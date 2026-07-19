# syntax=docker/dockerfile:1.7

FROM python:3.14.6-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

LABEL org.opencontainers.image.title="CareerOS Local backend" \
      org.opencontainers.image.description="Local-first personal career agent API" \
      org.opencontainers.image.source="https://github.com/ejupi-djenis30/careeros-local"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HOME=/app/data/home \
    XDG_CONFIG_HOME=/app/data/config \
    XDG_CACHE_HOME=/app/data/cache

WORKDIR /app

RUN groupadd --gid 10001 careernos \
    && useradd --uid 10001 --gid careernos --no-create-home --shell /usr/sbin/nologin careernos

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements.lock

COPY alembic ./alembic
COPY alembic.ini ./
COPY backend ./backend
COPY docker/backend-entrypoint.sh /usr/local/bin/careeros-entrypoint

RUN chmod 0555 /usr/local/bin/careeros-entrypoint \
    && install -d -o careernos -g careernos -m 0700 /app/data

USER careernos:careernos

VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3)"]

ENTRYPOINT ["careeros-entrypoint"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
