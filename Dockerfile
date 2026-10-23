# Base image with fixed version and digest.
# The tag is only for humans, Docker uses the digest.
FROM python:3.14.9-slim@sha256:0514bc76712d64f8bb48adcb95b1ab0d88c69fee95d62fe4c18ee948bee9b1e1

# No .pyc files (the container is read-only anyway)
# Logs go out directly, without buffering, so "docker logs" shows them right away
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATUSPAGE_CONFIG=/config/config.toml

WORKDIR /app

# Dependencies first, code second.
# Docker caches every step. If only the code changes, pip does not run again.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# Run as user "nobody", not as root
USER 65534:65534

EXPOSE 8000

# Docker calls /healthz every 30 seconds. A 503 makes urlopen fail, so the container becomes "unhealthy".
# urllib is in the standard library, so we do not need curl in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

# --no-access-log: otherwise every healthcheck would be logged. Requests are in the Traefik access log later.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]