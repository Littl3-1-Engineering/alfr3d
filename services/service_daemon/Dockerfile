FROM python:3.14.2-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /var/run/alfr3ddaemon /var/log/alfr3d

CMD ["python", "alfr3ddaemon.py", "start"]
