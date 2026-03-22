FROM python:3.14.3-slim

WORKDIR /app

COPY service_user/requirements.txt .

RUN pip install -r requirements.txt

COPY service_user/ ./
COPY common/ ./common/

CMD ["python", "app.py"]
