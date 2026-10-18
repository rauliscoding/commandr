# syntax=docker/dockerfile:1.7
# The public edge: Caddy serving the built SPA and proxying the API.
# Build from the repository root:
#   docker build -f deploy/docker/web.Dockerfile -t commandr-web .

FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY deploy/compose/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
