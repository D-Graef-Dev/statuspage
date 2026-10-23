# statuspage

Public status page for my self-hosted server ([selfhosted-cloud](https://github.com/D-Graef-Dev/selfhosted-cloud)).
Written in Python with FastAPI. Built as a 3-day project during my FIAE retraining.

## What it does

A background loop runs all checks from `config.toml` every 30 seconds:

| Type | Check |
|---|---|
| `http` | Status code of a URL |
| `json` | Reads one field from a JSON response and maps its value to a status |
| `tls` | Days until the certificate expires |

A service is shown as down after 3 failed checks in a row. Unknown values and errors count as down.

Henria reports its state on `/status` (`open`, `announced`, `maintenance`, `down`). A status code check would not see maintenance, because it also returns 200. The `json` check reads the field instead.

Checks with `public = false` only show up in the log. I use them for the admin interfaces: they must answer `403` from outside the VPN. A `200` means the VPN restriction is gone.

## Endpoints

| Path | |
|---|---|
| `/` | Status page |
| `/api/status` | Same data as JSON |
| `/healthz` | `503` if the last check round is older than 3 intervals |

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:STATUSPAGE_CONFIG = "config.example.toml"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

One round without the web server:

```powershell
.\.venv\Scripts\python.exe -m app.checks config.example.toml
```

The config is checked with Pydantic at startup. Unknown fields or wrong types stop the start.

## Docker

```bash
docker build -t statuspage:dev .
docker run -d --name statuspage --read-only --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 \
  --mount type=bind,source=$PWD/config.toml,target=/config/config.toml,readonly \
  statuspage:dev
```

Runs as `nobody` (65534) with a read-only filesystem. The healthcheck calls `/healthz`.

Tested on the server in the `monitoring` network. All checks worked, including `Monitoring`.

## Known limitations

- Runs on the same server it checks. If the server is down, the page is down too.
- The `Monitoring` check only works when the container is in the `monitoring` Docker network.
- Admin checks give wrong results when run from a machine inside the VPN.
- Only direct dependencies are pinned. FastAPI's own dependencies are not locked yet.
- State is only kept in memory. No history after a restart.

## Planned

- Image on GHCR
- GitHub Action: tests, build, Trivy scan
- Deployment on the server behind Traefik
- SQLite history with uptime and incidents
- `/metrics` for Prometheus
- Lock file for all dependencies

## How it was made

Design, research and testing by me. The code was written with Claude (Anthropic) as a mentor.