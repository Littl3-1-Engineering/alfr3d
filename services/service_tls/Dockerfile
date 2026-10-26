# syntax=docker/dockerfile:1
# TLS sidecar: owns the local CA key and re-issues the nginx leaf cert when the host's
# addresses change. Runs with network_mode: host (see docker-compose.yml) so it sees the
# real LAN interfaces rather than the container bridge.
FROM python:3.14-slim

WORKDIR /app

COPY service_tls/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY service_tls/app.py service_tls/local_tls.py ./

CMD ["python", "app.py"]
