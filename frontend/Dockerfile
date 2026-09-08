# syntax=docker/dockerfile:1.7

FROM node:24.20.0-alpine3.24@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build

ENV NODE_ENV=production
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --ignore-scripts

COPY frontend ./
COPY scripts/check_node_version.mjs /app/scripts/check_node_version.mjs
COPY scripts/validate_frontend_bundle.mjs /app/scripts/validate_frontend_bundle.mjs
COPY THIRD_PARTY_NOTICES.txt /app/THIRD_PARTY_NOTICES.txt
RUN npm run build

FROM nginx:1.31.5-alpine3.24-slim@sha256:3b171d7224b669faa3cc2137fea0a65301791df1ec1f271ebd2a2b7461f7fade

ARG CAREEROS_BUILD_REVISION=unknown

LABEL org.opencontainers.image.title="CareerOS Local web" \
      org.opencontainers.image.description="Local-first CareerOS browser interface" \
      org.opencontainers.image.source="https://github.com/ejupi-djenis30/careeros-local" \
      org.opencontainers.image.version="1.11.1" \
      org.opencontainers.image.revision="${CAREEROS_BUILD_REVISION}" \
      org.opencontainers.image.licenses="MIT"

# Keep OS security fixes current even while the upstream image digest is pinned.
RUN apk upgrade --no-cache \
    && rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx-main.conf /etc/nginx/nginx.conf
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/nginx-api-proxy.conf /etc/nginx/conf.d/careeros-api-proxy.inc
COPY LICENSE THIRD_PARTY_NOTICES.txt /usr/share/licenses/careeros-local/
RUN chmod -R a-w /usr/share/nginx/html \
    && chmod 0444 \
        /usr/share/licenses/careeros-local/LICENSE \
        /usr/share/licenses/careeros-local/THIRD_PARTY_NOTICES.txt

USER nginx:nginx

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=5 \
    CMD ["wget", "--quiet", "--output-document=-", "http://127.0.0.1:8080/"]

ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
