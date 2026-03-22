FROM python:3.14.2-slim

WORKDIR /app

COPY service_daemon/requirements.txt .
RUN pip install -r requirements.txt

COPY service_daemon/ ./
COPY common/ ./common/

RUN mkdir -p /var/run/alfr3ddaemon /var/log/alfr3d

CMD ["python", "alfr3ddaemon.py", "start"]
