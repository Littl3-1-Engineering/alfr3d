# syntax=docker/dockerfile:1
FROM python:3.11.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    docker.io \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY service_api/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

RUN groupdel docker; groupadd -g 993 docker; \
    groupadd -r -g 1000 alfr3d && useradd -r -u 1000 -g alfr3d alfr3d \
    && usermod -aG docker alfr3d

COPY service_api/app.py .
COPY service_api/tree_of_alfr3d.py .
COPY common/ ./common/

RUN chown -R alfr3d:alfr3d /app

COPY service_api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5001

USER alfr3d

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
