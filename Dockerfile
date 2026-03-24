# ─────────────────────────────────────
# Job Hunter AI — Dockerfile
# ─────────────────────────────────────
# Multi-stage build: Python backend + static frontend
# Usage:
#   docker build -t job-hunter-ai .
#   docker run -p 8000:8000 --env-file .env job-hunter-ai

# === Stage 1: Build frontend ===
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

# === Stage 2: Python backend ===
FROM python:3.12-slim AS runtime

# System deps for psycopg2 and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend code
COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini .
COPY run.py .

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

# Default env
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV LOG_LEVEL=INFO
ENV DATABASE_URL=sqlite:///./data/job_hunter.db

# Data volume for SQLite persistence
VOLUME ["/app/data"]

EXPOSE 8000

# Run with gunicorn for production, uvicorn worker
# NOTE: Workers must be set to 1! If increased, APScheduler will spawn 
# duplicate search jobs in each worker process, leading to repeated queries.
CMD ["gunicorn", "backend.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "1", \
    "--timeout", "120"]
