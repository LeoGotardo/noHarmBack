# syntax=docker/dockerfile:1
#
# One image: the Vite bundle, the FastAPI app, and the nginx that fronts both.
#
# BUILD CONTEXT IS THE PARENT OF BOTH REPOS. noHarm and noHarmBack are separate
# git repos that live side by side, and a Dockerfile cannot reach outside its
# context, so the context has to be the directory holding them:
#
#     cd /path/that/contains/noHarm/ /path/that/contains/noHarmBack/
#     docker build -f noHarmBack/docker/Dockerfile -t noharm .
#
# CI therefore needs both repos checked out as siblings.

# ── Stage 1: the front-end bundle ──────────────────────────────────────────
FROM node:22-alpine AS frontend

# Vite inlines every VITE_* at build time — they are baked into the JS, not read
# at runtime, so they must arrive here and nowhere later. A missing one does not
# fail the build: it compiles to `undefined` and surfaces as a login that never
# works. None of them is a secret (the Firebase web config and the status table
# reach the browser regardless).
ARG VITE_API_URL=/api
ARG VITE_SOCKET_URL=
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_STORAGE_BUCKET
ARG VITE_FIREBASE_MESSAGING_SENDER_ID
ARG VITE_FIREBASE_APP_ID
ARG VITE_STATUS_CONSTANTS
ENV VITE_API_URL=$VITE_API_URL \
    VITE_SOCKET_URL=$VITE_SOCKET_URL \
    VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_STORAGE_BUCKET=$VITE_FIREBASE_STORAGE_BUCKET \
    VITE_FIREBASE_MESSAGING_SENDER_ID=$VITE_FIREBASE_MESSAGING_SENDER_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID \
    VITE_STATUS_CONSTANTS=$VITE_STATUS_CONSTANTS

WORKDIR /build
# Manifests first: this layer only rebuilds when a dependency actually changes,
# not on every source edit.
COPY noHarm/package.json noHarm/package-lock.json ./
RUN npm ci
COPY noHarm/ ./
RUN npm run build

# ── Stage 2: python deps ───────────────────────────────────────────────────
# Kept separate so the toolchain needed to compile wheels never ships.
FROM python:3.12.3-slim AS pydeps

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY noHarmBack/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

# ── Stage 3: runtime ───────────────────────────────────────────────────────
FROM python:3.12.3-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx supervisor libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --create-home --shell /usr/sbin/nologin appuser

COPY --from=pydeps /install /usr/local

WORKDIR /app
COPY noHarmBack/src/       ./src/
COPY noHarmBack/alembic/   ./alembic/
COPY noHarmBack/alembic.ini ./

# The SPA. Everything under here is world-readable static output.
COPY --from=frontend /build/dist/ /usr/share/nginx/html/

COPY noHarmBack/docker/nginx.conf            /etc/nginx/nginx.conf
COPY noHarmBack/docker/app_locations.conf    /etc/nginx/app_locations.conf
# One of these becomes /etc/nginx/server.conf at boot, per TLS_MODE. The
# entrypoint also writes /etc/nginx/forwarded.conf, which both include paths in
# nginx.conf expect to exist — so nginx is only ever started through it.
COPY noHarmBack/docker/server.alb.conf       /etc/nginx/server.alb.conf
COPY noHarmBack/docker/server.tls.conf       /etc/nginx/server.tls.conf
COPY noHarmBack/docker/proxy_headers.conf    /etc/nginx/proxy_headers.conf
COPY noHarmBack/docker/security_headers.conf /etc/nginx/security_headers.conf
COPY noHarmBack/docker/supervisord.conf      /etc/supervisor/supervisord.conf
COPY noHarmBack/docker/entrypoint.sh         /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p /var/www/certbot /etc/nginx/certs \
 && chown -R appuser:appuser /app

# nginx binds 443, which needs root; it drops its workers to www-data itself.
# uvicorn runs as appuser — see supervisord.conf.
# TLS_MODE picks which of the two ports is actually served: `alb` (default)
# listens on 80 alone and expects a load balancer to hold the certificate;
# `container` terminates TLS on 443 and needs the pair mounted at
# /etc/nginx/certs. See entrypoint.sh.
EXPOSE 80 443

# Hits the app through nginx, so a green check means the whole chain answers,
# not just that a process is alive. Plain :80 on purpose: it is the only port
# both TLS modes listen on, and in container mode /health is exempted from the
# redirect for exactly this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fs http://127.0.0.1/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
