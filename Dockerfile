FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo "=== Files in /app ===" && ls -la /app/

EXPOSE 5000

CMD ["python", "bot_runner.py"]
