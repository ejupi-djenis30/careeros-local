# syntax=docker/dockerfile:1.7

FROM node:24.18.0-alpine3.24@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build

ENV NODE_ENV=production
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --ignore-scripts

COPY frontend ./
COPY scripts/check_node_version.mjs /app/scripts/check_node_version.mjs
COPY scripts/validate_frontend_bundle.mjs /app/scripts/validate_frontend_bundle.mjs
COPY THIRD_PARTY_NOTICES.txt /app/THIRD_PARTY_NOTICES.txt
RUN npm run build

FROM nginx:1.31.3-alpine3.24-slim@sha256:45b82ed5f285b90d63df07ba70430fdd8f25624b416617d9e6dc93412b2006dc

ARG CAREEROS_BUILD_REVISION=unknown

LABEL org.opencontainers.image.title="CareerOS Local web" \
      org.opencontainers.image.description="Local-first CareerOS browser interface" \
      org.opencontainers.image.source="https://github.com/ejupi-djenis30/careeros-local" \
      org.opencontainers.image.version="1.10.0" \
      org.opencontainers.image.revision="${CAREEROS_BUILD_REVISION}" \
      org.opencontainers.image.licenses="MIT"

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

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
