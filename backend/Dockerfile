FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Data directory for persistent SQLite volume
RUN mkdir -p /data

# Default DB path points to the volume
ENV DATABASE_URL=sqlite+aiosqlite:////data/trading.db

EXPOSE 8080

# Use shell form so $PORT env var from Render is resolved at runtime
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
