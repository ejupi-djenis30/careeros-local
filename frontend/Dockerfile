# syntax=docker/dockerfile:1.7

FROM node:22.23.1-alpine3.24@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS build

ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --include=dev --ignore-scripts

COPY . ./
RUN npm run build

FROM nginx:1.30.3-alpine3.23-slim@sha256:d5b51cfc7d55fc7a7bcf4d1d577b9c3738331df56d68f0b1d8ac9795b9470a5a

LABEL org.opencontainers.image.title="CareerOS Local web" \
      org.opencontainers.image.description="Local-first CareerOS browser interface"

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY nginx-main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER nginx:nginx

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=5 \
    CMD ["wget", "--quiet", "--output-document=-", "http://127.0.0.1:8080/"]

ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
