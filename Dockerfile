# Minimal image for the Telegram bot. Not used by the weekly runner
# (that runs on GitHub Actions). Build with:
#   docker build -t vc-actions-bot .
# Run with:
#   docker run --env-file .env vc-actions-bot
#
# For Fly.io: `fly launch` reads this Dockerfile and the bundled fly.toml.
FROM python:3.11-slim

WORKDIR /app

# Layer requirements separately so dependency installs cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Long-polling — no exposed ports needed.
CMD ["python", "-m", "chat.telegram_app"]
