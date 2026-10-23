# os reads the path of the config file from an environment variable
# html.escape makes sure no text from the config can break the HTML page
# logging writes status changes to the console (later: docker logs)
# asynccontextmanager is needed for the "lifespan": code that runs at start and stop
import asyncio
import html
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from app.checks import Tracker, run_all
from app.config import Config, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("statuspage")
# httpx would log every single request. We only want status changes.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Path of the config file. Default is config.toml, it can be changed with an environment variable.
CONFIG_PATH = os.environ.get("STATUSPAGE_CONFIG", "config.toml")

# Text and color for each status on the page.
LABELS = {
    "up": ("Operational", "#2e7d32"),
    "maintenance": ("Maintenance", "#1565c0"),
    "down": ("Down", "#c62828"),
    "unknown": ("Checking", "#757575"),
}


# Background loop: runs all checks, updates the shown status and waits.
# Only status changes are logged, otherwise the log would fill up every 30 seconds.
# The detail goes to the log, never to the page.
# The try/except keeps the loop alive even if something unexpected happens.
async def poll_loop(app: FastAPI, config: Config) -> None:
    tracker = Tracker(config.settings.failures_before_down)
    while True:
        try:
            results = await run_all(config)
            for result in results:
                old = app.state.status.get(result.name, {}).get("status")
                new = tracker.update(result)
                if new != old:
                    log.info("%s: %s -> %s (%s)", result.name, old, new, result.detail)
                app.state.status[result.name] = {"public": result.public, "status": new}
            app.state.last_round = time.time()
        except Exception:
            log.exception("check round failed")
        await asyncio.sleep(config.settings.interval_seconds)


# Lifespan: everything before "yield" runs at start, everything after it at stop.
# At start: load the config (a broken config stops the start right here) and start the loop.
# At stop: cancel the loop.
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config(CONFIG_PATH)
    app.state.config = config
    app.state.status = {c.name: {"public": c.public, "status": "unknown"} for c in config.check}
    app.state.last_round = 0.0
    task = asyncio.create_task(poll_loop(app, config))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


# Returns only the public checks as a simple dict: name -> status.
def public_status() -> dict[str, str]:
    return {name: entry["status"] for name, entry in app.state.status.items() if entry["public"]}


# The status page. It reloads itself every 30 seconds.
# Every text from the config goes through html.escape.
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    title = html.escape(app.state.config.title)
    rows = ""
    for name, status in public_status().items():
        label, color = LABELS[status]
        rows += f'<li><span>{html.escape(name)}</span><b style="color:{color}">{label}</b></li>\n'
    if app.state.last_round:
        checked = time.strftime("%H:%M:%S UTC", time.gmtime(app.state.last_round))
    else:
        checked = "not yet"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; color: #222; }}
ul {{ list-style: none; padding: 0; }}
li {{ display: flex; justify-content: space-between; padding: .8rem 0; border-bottom: 1px solid #ddd; }}
small {{ color: #757575; }}
</style>
</head>
<body>
<h1>{title}</h1>
<ul>
{rows}</ul>
<small>Last check: {checked}</small>
</body>
</html>"""


# Same data as JSON, for scripts or other tools.
@app.get("/api/status")
def api_status() -> dict:
    return {"last_check": app.state.last_round, "services": public_status()}


# Health endpoint for the Docker healthcheck.
# If the last round is older than 3 intervals, the loop is stuck: answer 503.
@app.get("/healthz")
def healthz():
    max_age = 3 * app.state.config.settings.interval_seconds
    if time.time() - app.state.last_round > max_age:
        return JSONResponse({"status": "stale"}, status_code=503)
    return {"status": "ok"}