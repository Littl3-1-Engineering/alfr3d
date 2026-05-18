# syntax=docker/dockerfile:1
FROM python:3.11.9-slim

WORKDIR /app

COPY service_speak/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

RUN groupadd -r -g 1000 alfr3d && useradd -r -u 1000 -g alfr3d alfr3d

COPY service_speak/*.py ./
COPY common/ ./common/

RUN mkdir -p /tmp/audio && chown -R alfr3d:alfr3d /tmp/audio

COPY service_speak/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER alfr3d

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
