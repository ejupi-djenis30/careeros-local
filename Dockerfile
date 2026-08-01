# syntax=docker/dockerfile:1.7

FROM python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d

ARG CAREEROS_BUILD_REVISION=unknown

LABEL org.opencontainers.image.title="CareerOS Local backend" \
      org.opencontainers.image.description="Local-first personal career agent API" \
      org.opencontainers.image.source="https://github.com/ejupi-djenis30/careeros-local" \
      org.opencontainers.image.version="1.10.0" \
      org.opencontainers.image.revision="${CAREEROS_BUILD_REVISION}" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HOME=/app/data/home \
    XDG_CONFIG_HOME=/app/data/config \
    XDG_CACHE_HOME=/app/data/cache

WORKDIR /app

RUN addgroup -S -g 10001 careernos \
    && adduser -S -D -H -u 10001 -G careernos -s /sbin/nologin careernos

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements.lock \
    && python -m pip uninstall --yes pip \
    && rm -rf \
        /usr/local/bin/idle* \
        /usr/local/bin/pip* \
        /usr/local/lib/python3.12/ensurepip \
        /usr/local/lib/python3.12/site-packages/pip \
        /usr/local/lib/python3.12/site-packages/pip-*.dist-info

COPY alembic.ini ./
COPY THIRD_PARTY_NOTICES.txt ./
COPY LICENSE THIRD_PARTY_NOTICES.txt /usr/share/licenses/careeros-local/
COPY backend ./backend
COPY desktop/__init__.py desktop/backend_main.py ./desktop/
COPY docker/backend-entrypoint.sh /usr/local/bin/careeros-entrypoint

RUN chmod 0555 /usr/local/bin/careeros-entrypoint \
    && chmod 0444 \
        /usr/share/licenses/careeros-local/LICENSE \
        /usr/share/licenses/careeros-local/THIRD_PARTY_NOTICES.txt \
    && mkdir -p /app/data \
    && chown careernos:careernos /app/data \
    && chmod 0700 /app/data

USER careernos:careernos

VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3)"]

ENTRYPOINT ["careeros-entrypoint"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-server-header", "--no-access-log"]
