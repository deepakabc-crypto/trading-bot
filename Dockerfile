FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Debug: verify files are copied (remove after confirming)
RUN ls -la /app/

# Expose port for Flask dashboard
EXPOSE 5000

# Run the bot
CMD ["python", "bot_runner.py"]
