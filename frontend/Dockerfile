# syntax=docker/dockerfile:1.7

FROM node:24.21.0-alpine3.24@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build

ENV NODE_ENV=production
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --ignore-scripts

COPY frontend ./
COPY scripts/check_node_version.mjs /app/scripts/check_node_version.mjs
COPY scripts/validate_frontend_bundle.mjs /app/scripts/validate_frontend_bundle.mjs
COPY THIRD_PARTY_NOTICES.txt /app/THIRD_PARTY_NOTICES.txt
RUN npm run build

FROM nginx:1.31.6-alpine3.24-slim@sha256:f761b94f2cb9e8e05e2943d5f773609596113ef69b54e2433a996d109a8f78b7

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
