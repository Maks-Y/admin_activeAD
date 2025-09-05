FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY ai/nlp.py ai/__init__.py ./ai/
COPY ad ./ad

CMD ["python", "-m", "bot.main"]
