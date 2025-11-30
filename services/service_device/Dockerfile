FROM python:3.9-slim

# Install arp-scan and iproute2
RUN apt-get update && apt-get install -y arp-scan iproute2 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

# Run as root to allow arp-scan
USER root

CMD ["python", "app.py"]