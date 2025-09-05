FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY ai ./ai

CMD ["python", "bot/main.py"]
