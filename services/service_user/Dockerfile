# syntax=docker/dockerfile:1
FROM python:3.14.0-slim

WORKDIR /app

COPY service_user/requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN groupadd -r -g 1000 alfr3d && useradd -r -u 1000 -g alfr3d alfr3d

COPY service_user/ ./
COPY common/ ./common/

RUN chown -R alfr3d:alfr3d /app

USER alfr3d

CMD ["python", "app.py"]
