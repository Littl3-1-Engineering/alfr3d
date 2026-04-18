# syntax=docker/dockerfile:1
FROM python:3.14.0-slim

WORKDIR /app

COPY service_daemon/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN groupadd -r -g 1000 alfr3d && useradd -r -u 1000 -g alfr3d alfr3d

COPY service_daemon/ ./
COPY common/ ./common/

RUN mkdir -p /var/run/alfr3ddaemon /var/log/alfr3d && chown -R alfr3d:alfr3d /var/run/alfr3ddaemon /var/log/alfr3d

USER alfr3d

CMD ["python", "alfr3ddaemon.py", "start"]
