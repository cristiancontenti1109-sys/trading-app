FROM python:3.11-slim

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Build React frontend and copy into backend
RUN cd web && npm install && npm run build && \
    mkdir -p /app/backend/frontend_dist && \
    cp -r dist/. /app/backend/frontend_dist/

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

WORKDIR /app/backend

EXPOSE 8001

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
