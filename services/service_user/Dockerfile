# syntax=docker/dockerfile:1
FROM python:3.14-slim

WORKDIR /app

COPY service_user/requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY service_user/ ./
COPY common/ ./common/

CMD ["python", "app.py"]
