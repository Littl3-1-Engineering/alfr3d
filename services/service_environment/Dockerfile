FROM python:3.9-slim

WORKDIR /app

COPY service_environment/requirements.txt .

RUN pip install -r requirements.txt

COPY service_environment/ ./
COPY common/ ./common/

CMD ["python", "environment.py"]
