# syntax=docker/dockerfile:1
# service_sa: situational awareness (LF-1a). One image, two compose entries -- sa-awareness runs
# awareness.py, sa-learner runs learner.py (see docker-compose.yml).
FROM python:3.14-slim

WORKDIR /app

COPY service_sa/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN groupadd -r -g 1000 alfr3d && useradd -r -u 1000 -g alfr3d alfr3d

COPY service_sa/ ./
COPY common/ ./common/

# The Parquet lake (LF-1b) mounts here on sa-learner. Created and chowned in the image so the
# named volume inherits uid 1000 ownership on first use; otherwise it comes up root-owned and the
# non-root learner can't write to it.
RUN mkdir -p /lake && chown alfr3d:alfr3d /lake

USER alfr3d

CMD ["python", "awareness.py"]
