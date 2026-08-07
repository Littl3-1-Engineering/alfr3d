# syntax=docker/dockerfile:1
# One-shot DB migration runner: applies setup/migrations chain via Alembic.
# Build context must be ./setup (dockerfile: ./migrations/Dockerfile).
FROM python:3.14-slim

WORKDIR /setup/migrations

COPY migrations/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY migrations/ ./
COPY *.sql /setup/
COPY createTables.sql /setup/

ENV MYSQL_DATABASE=${MYSQL_DATABASE:-mysql} \
    MYSQL_PORT=${MYSQL_PORT:-3306} \
    MYSQL_USER=${MYSQL_USER:-root} \
    MYSQL_PSWD=${MYSQL_PSWD:-} \
    MYSQL_NAME=${MYSQL_NAME:-alfr3d_db}

CMD ["alembic", "upgrade", "head"]
