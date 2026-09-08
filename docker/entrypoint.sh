#!/bin/bash
# Container entrypoint: pick the TLS shape, check what must be true, migrate if
# asked, hand over.
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

TLS_MODE="${TLS_MODE:-alb}"

# ── Database URLs ──────────────────────────────────────────────────────────
# config.py wants DATABASE_URL and DATABASE_URL_UNPOOLED as whole strings, but
# on RDS the password lives in its own secret (the one RDS rotates), so keeping
# the URLs as literals would mean storing that password a second time, by hand,
# and re-editing it on every rotation. Compose them here instead when they are
# not supplied: the password arrives as DATABASE_PASSWORD straight from the
# managed secret and exists in exactly one place.
#
# Anything already set wins, so compose.prod.yaml and a local run can keep
# passing full URLs and never reach this.
composeDbUrls() {
    local host="${DATABASE_HOST:-}" name="${DATABASE_NAME:-}"
    local user="${DATABASE_USER:-}" password="${DATABASE_PASSWORD:-}"

    if [[ -z "$host" || -z "$name" || -z "$user" || -z "$password" ]]; then
        log "FATAL: DATABASE_URL is unset and cannot be composed."
        log "Supply DATABASE_URL, or all of DATABASE_HOST, DATABASE_NAME,"
        log "DATABASE_USER and DATABASE_PASSWORD."
        exit 1
    fi

    # A generated password contains characters that are syntax in a URL — `/`,
    # `@`, `#`, `?` all cut the string somewhere else than intended, and the
    # failure is a connection to the wrong place rather than an error.
    local encoded
    encoded="$(DBP="$password" python3 -c \
        'import os,urllib.parse;print(urllib.parse.quote(os.environ["DBP"], safe=""))')"

    # RDS is created with rds.force_ssl=1, which refuses a plaintext session.
    # libpq's default (`prefer`) would still negotiate TLS, but it downgrades
    # silently if the server ever stops offering it — naming the mode makes the
    # requirement explicit instead of incidental.
    local query=""
    [[ -n "${DATABASE_SSLMODE:-}" ]] && query="?sslmode=${DATABASE_SSLMODE}"

    export DATABASE_URL="postgresql://${user}:${encoded}@${host}:${DATABASE_PORT:-5432}/${name}${query}"
    log "composed DATABASE_URL for ${user}@${host}/${name}"

    # Alembic must not go through a pooler: pgBouncer and RDS Proxy both break
    # DDL in a transaction. DATABASE_HOST_UNPOOLED is the instance endpoint for
    # the day a pooler is put in front; without one the two are the same host.
    export DATABASE_URL_UNPOOLED="postgresql://${user}:${encoded}@${DATABASE_HOST_UNPOOLED:-$host}:${DATABASE_PORT:-5432}/${name}${query}"
}

if [[ -z "${DATABASE_URL:-}" ]]; then
    composeDbUrls
elif [[ -z "${DATABASE_URL_UNPOOLED:-}" ]]; then
    log "FATAL: DATABASE_URL is set but DATABASE_URL_UNPOOLED is not."
    log "Alembic uses the unpooled one; set both or neither."
    exit 1
fi

# ── One-shot migration task ────────────────────────────────────────────────
# `docker run <image> migrate` (ECS: a run-task with command=["migrate"]) runs
# the upgrade and exits, instead of serving. Handled before anything else
# because a release task has no certificate mounted and no load balancer in
# front — neither TLS branch below applies to it.
if [[ "${1:-}" == "migrate" ]]; then
    log "migration task: alembic upgrade head (APP_ENV=${APP_ENV:-prod})"
    cd /app && alembic upgrade head
    log "migrations done"
    exit 0
fi

# ── One-shot account purge ─────────────────────────────────────────────────
# `docker compose run --rm app purge-accounts` permanently deletes accounts
# whose deletion grace window has closed. Cron runs this on the live instance;
# see docs/operations.md. Same placement as migrate, for the same reason: it
# serves nothing and needs neither a certificate nor a load balancer.
#
# Its exit code is meaningful — non-zero means at least one account could not be
# purged — so it must not be swallowed by the TLS branches below.
if [[ "${1:-}" == "purge-accounts" ]]; then
    log "purge task: deleting accounts past the deletion grace window"
    cd /app/src && python -m jobs.purgeAccounts
    exit $?
fi

# ── TLS shape ──────────────────────────────────────────────────────────────
# alb       — TLS ends at an AWS load balancer (ACM certificate). The container
#             serves plain :80 and never sees a certificate. This is the default
#             because it is the deployed shape.
# container — nginx terminates TLS itself and the certificate pair is a hard
#             dependency. compose.prod.yaml and any direct-to-internet host.
case "$TLS_MODE" in
    alb)
        # Without real_ip the client address is the load balancer's ENI, so
        # every request in the world shares one rate-limit bucket and the first
        # busy minute locks the API for everybody. Refusing to start beats
        # discovering that under load.
        if [[ -z "${TRUSTED_PROXY_CIDRS:-}" ]]; then
            log "FATAL: TLS_MODE=alb needs TRUSTED_PROXY_CIDRS."
            log "Set it to the subnets the load balancer's ENIs live in, space"
            log "or comma separated — e.g. TRUSTED_PROXY_CIDRS='10.0.0.0/16'."
            log "Everything listed can forge X-Forwarded-For, so name the VPC"
            log "subnets and nothing wider."
            exit 1
        fi

        {
            echo "# Generated by entrypoint.sh — TLS_MODE=alb."
            echo "#"
            echo "# real_ip_recursive walks X-Forwarded-For right to left and stops at the"
            echo "# first address not covered below. The ALB appends the connecting client"
            echo "# to whatever the caller sent, so that address is the client and anything"
            echo "# the caller invented sits harmlessly to its left."
            for cidr in ${TRUSTED_PROXY_CIDRS//,/ }; do
                echo "set_real_ip_from $cidr;"
            done
            echo "real_ip_header    X-Forwarded-For;"
            echo "real_ip_recursive on;"
            echo
            echo "# The browser's leg is https even though this hop is not."
            echo "map \$http_x_forwarded_proto \$forwardedProto {"
            echo "    default \$scheme;"
            echo "    https   https;"
            echo "    http    http;"
            echo "}"
        } > /etc/nginx/forwarded.conf

        cp /etc/nginx/server.alb.conf /etc/nginx/server.conf
        log "TLS_MODE=alb — plain :80, trusting X-Forwarded-For from ${TRUSTED_PROXY_CIDRS}"
        ;;

    container)
        # Fail loudly now rather than letting nginx fail to start behind
        # supervisor, where the reason scrolls past in a restart loop.
        for f in /etc/nginx/certs/fullchain.pem /etc/nginx/certs/privkey.pem; do
            if [[ ! -r "$f" ]]; then
                log "FATAL: $f missing or unreadable."
                log "Mount the certificate pair at /etc/nginx/certs (see compose.prod.yaml),"
                log "or run with TLS_MODE=alb and terminate TLS at the load balancer."
                exit 1
            fi
        done

        {
            echo "# Generated by entrypoint.sh — TLS_MODE=container."
            echo "#"
            echo "# No real_ip setup: nothing sits in front of nginx, so \$remote_addr is"
            echo "# already the peer off the socket and X-Forwarded-For is not to be"
            echo "# believed from anyone."
            echo "map \$host \$forwardedProto {"
            echo "    default \$scheme;"
            echo "}"
        } > /etc/nginx/forwarded.conf

        cp /etc/nginx/server.tls.conf /etc/nginx/server.conf
        log "TLS_MODE=container — terminating TLS on :443"
        ;;

    *)
        log "FATAL: TLS_MODE must be 'alb' or 'container', got '$TLS_MODE'."
        exit 1
        ;;
esac

# ── The one variable that must never be set here ──────────────────────────
# It makes firebase-admin skip signature and expiry checks entirely, so anyone
# can authenticate as anyone. It belongs to dev compose and the test suite.
if [[ -n "${FIREBASE_AUTH_EMULATOR_HOST:-}" ]]; then
    log "FATAL: FIREBASE_AUTH_EMULATOR_HOST is set. That disables Firebase"
    log "token verification completely — refusing to start."
    exit 1
fi

# ── Migrations ─────────────────────────────────────────────────────────────
# Off by default. Running them from every container means N instances racing
# the same upgrade on a scale-out; opt in on one, or run it as a release task.
if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
    log "running alembic upgrade head (APP_ENV=${APP_ENV:-prod})"
    cd /app && alembic upgrade head
    log "migrations done"
fi

log "starting nginx + uvicorn"
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
