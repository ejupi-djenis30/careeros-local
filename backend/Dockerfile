FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code and migrations
COPY backend ./backend
COPY alembic ./alembic
COPY alembic.ini .

# Run as non-root for security
RUN addgroup --system appuser && adduser --system --ingroup appuser --home /home/appuser appuser \
    && chown -R appuser:appuser /app /home/appuser
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Migrations are handled by docker-compose `command:` which has the correct DATABASE_URL.
# This CMD is the fallback for standalone runs (dev/test).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
