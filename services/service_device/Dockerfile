# syntax=docker/dockerfile:1
FROM python:3.11.9-slim

# Install arp-scan and iproute2
RUN apt-get update && apt-get install -y arp-scan iproute2 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY service_device/requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY service_device/ ./
COPY common/ ./common/

# Run as root to allow arp-scan
USER root

CMD ["python", "app.py"]
