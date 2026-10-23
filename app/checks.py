# asyncio runs all checks at the same time instead of one after another
# ssl and time are needed for the TLS check
# dataclass creates a simple class for our results without much code
# httpx is the HTTP client, it can do async (requests can not)
import asyncio
import ssl
import sys
import time
from dataclasses import dataclass

import httpx

from app.config import Config, HttpCheck, JsonCheck, TlsCheck, load_config


# Result of one check in one round.
# status is "up", "maintenance" or "down".
# detail is only for us (log, later /metrics), never shown on the public page.
@dataclass
class Result:
    name: str
    public: bool
    status: str
    detail: str


# HTTP check: call the URL and compare the status code.
# Redirects are not followed, so a 302 stays a 302.
async def check_http(client: httpx.AsyncClient, check: HttpCheck) -> tuple[str, str]:
    response = await client.get(check.url)
    if response.status_code == check.expect_status:
        return "up", f"status {response.status_code}"
    return "down", f"expected {check.expect_status}, got {response.status_code}"


# JSON check: call the URL, read one field and look up its value in "states".
# Everything we do not understand counts as down:
# wrong status code, broken JSON, missing field or a value that is not in "states".
async def check_json(client: httpx.AsyncClient, check: JsonCheck) -> tuple[str, str]:
    response = await client.get(check.url)
    if response.status_code != 200:
        return "down", f"expected 200, got {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        return "down", "response is not valid JSON"
    if not isinstance(data, dict):
        return "down", "JSON is not an object"
    value = data.get(check.field)
    if not isinstance(value, str):
        return "down", f"field '{check.field}' missing or not a string"
    return check.states.get(value, "down"), f"{check.field}={value}"


# TLS check: open a TLS connection, read the expiry date of the certificate
# and count the days that are left.
# The default context checks the certificate. An invalid certificate fails here already.
async def check_tls(check: TlsCheck) -> tuple[str, str]:
    context = ssl.create_default_context()
    reader, writer = await asyncio.open_connection(check.host, check.port, ssl=context)
    try:
        cert = writer.get_extra_info("peercert")
    finally:
        writer.close()
        await writer.wait_closed()
    expires = ssl.cert_time_to_seconds(cert["notAfter"])
    days_left = int((expires - time.time()) // 86400)
    if days_left >= check.min_days_valid:
        return "up", f"{days_left} days left"
    return "down", f"only {days_left} days left"


# Runs one check and decides by its type which function is used.
# wait_for stops the check after timeout_seconds.
# Every error becomes "down", so one broken check can not stop the others.
async def run_check(client: httpx.AsyncClient, check, timeout: int) -> Result:
    try:
        match check:
            case HttpCheck():
                coro = check_http(client, check)
            case JsonCheck():
                coro = check_json(client, check)
            case TlsCheck():
                coro = check_tls(check)
        status, detail = await asyncio.wait_for(coro, timeout)
    except TimeoutError:
        status, detail = "down", f"timeout after {timeout}s"
    except Exception as error:
        status, detail = "down", f"{type(error).__name__}: {error}"
    return Result(check.name, check.public, status, detail)


# Runs all checks of the config at the same time and returns the results
# in the same order as in the config file.
async def run_all(config: Config) -> list[Result]:
    timeout = config.settings.timeout_seconds
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        tasks = [run_check(client, check, timeout) for check in config.check]
        return await asyncio.gather(*tasks)


# Remembers the shown status per check across rounds.
# "down" is only shown after failures_before_down failed rounds in a row,
# so one single timeout does not cause a false alarm.
# Before that, the last shown status stays. At the start it is "unknown".
class Tracker:
    def __init__(self, failures_before_down: int):
        self.failures_before_down = failures_before_down
        self.failures: dict[str, int] = {}
        self.shown: dict[str, str] = {}

    def update(self, result: Result) -> str:
        if result.status == "down":
            self.failures[result.name] = self.failures.get(result.name, 0) + 1
            if self.failures[result.name] >= self.failures_before_down:
                self.shown[result.name] = "down"
        else:
            self.failures[result.name] = 0
            self.shown[result.name] = result.status
        return self.shown.get(result.name, "unknown")


# Run one round from the console, without web server:
# python -m app.checks config.example.toml
if __name__ == "__main__":
    config = load_config(sys.argv[1])
    for result in asyncio.run(run_all(config)):
        print(f"{result.status:12} {result.name:20} {result.detail}")