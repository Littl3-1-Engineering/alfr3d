FROM python:3.11-slim

WORKDIR /app

COPY service_speak/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service_speak/*.py ./
COPY common/ ./common/

# Create audio directory
RUN mkdir -p /tmp/audio

CMD ["python", "app.py"]
