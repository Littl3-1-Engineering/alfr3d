# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

COPY service_environment/requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY service_environment/ ./
COPY common/ ./common/

CMD ["python", "environment.py"]
