# syntax=docker/dockerfile:1
# One-shot self-service updater (todo/todo_selfservice_release_update.md). service-api spawns
# this as `docker run -d --rm` via its existing docker.sock -- it is never declared as a
# long-running compose service (profiles: ["tools"] in docker-compose.yml keeps it out of a
# plain `docker compose up -d`). docker:27-cli ships the docker CLI and the compose v2 plugin
# together, avoiding the v1/v2-mixing trap already hit once
# (todo/todo_compose_container_name_collision.md).
FROM docker:27-cli

RUN apk add --no-cache git bash jq

COPY run_update.sh /run_update.sh
RUN chmod +x /run_update.sh

ENTRYPOINT ["/run_update.sh"]
