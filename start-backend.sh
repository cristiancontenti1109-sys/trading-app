#!/bin/bash
set -e

cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it to add API keys"
fi

echo "Starting backend on http://localhost:8000"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
