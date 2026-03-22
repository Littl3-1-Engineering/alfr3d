FROM python:3.9-slim

WORKDIR /app

# Install Docker CLI
RUN apt-get update && apt-get install -y \
    docker.io \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY service_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service_api/app.py .
COPY service_api/tree_of_alfr3d.py .
COPY common/ ./common/

EXPOSE 5001

CMD ["python", "app.py"]
