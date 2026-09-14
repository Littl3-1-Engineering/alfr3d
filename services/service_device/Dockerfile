# syntax=docker/dockerfile:1
FROM python:3.14-slim

# Install arp-scan and iproute2
RUN apt-get update && apt-get install -y arp-scan iproute2 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY service_device/requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY service_device/ ./
COPY common/ ./common/

# checkov:skip=CKV_DOCKER_8:arp-scan needs raw sockets on the host network (network_mode: host); no non-root path available
# Run as root to allow arp-scan
USER root

CMD ["python", "app.py"]
