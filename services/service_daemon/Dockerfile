# syntax=docker/dockerfile:1
FROM python:3.14-slim

WORKDIR /app

COPY service_daemon/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY service_daemon/ ./
COPY common/ ./common/

RUN mkdir -p /var/run/alfr3ddaemon /var/log/alfr3d

CMD ["python", "alfr3ddaemon.py", "start"]
