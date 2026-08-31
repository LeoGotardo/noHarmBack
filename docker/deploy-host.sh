#!/usr/bin/env bash
# Build here, ship the image, restart there.
#
# Run from the directory that holds BOTH repos — noHarm/ and noHarmBack/ — the
# same context the Dockerfile needs, because stage 1 compiles the front-end.
#
#   ./noHarmBack/docker/deploy-host.sh
#
# Why the build does not happen on the server: the instance is a t3.micro with
# 913 MB of RAM, and `vite build` needs more than that. Node gets OOM-killed
# partway through and the error names a heap limit, not the machine.
#
# The image travels over SSH rather than through a registry — no ECR, no
# credentials on the box, nothing to pay for. It is ~600 MB compressed on the
# wire, so this is minutes, not seconds.
#
# NOTE: .github/workflows/deploy.yml does NOT drive this deployment. It targets
# the ECS stack in infra/, which is provisioned by nothing right now. This
# script is the deploy.
set -euo pipefail

HOST="${NOHARM_HOST:-ec2-user@ec2-54-204-219-47.compute-1.amazonaws.com}"
KEY="${NOHARM_SSH_KEY:-noharm-ssh.pem}"
REMOTE_DIR="~/noHarmBack/docker"

[[ -d noHarm && -d noHarmBack ]] || {
    echo "run this from the directory containing noHarm/ and noHarmBack/" >&2
    exit 1
}
[[ -r "$KEY" ]] || { echo "ssh key not readable at $KEY" >&2; exit 1; }

ssh_() { ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST" "$@"; }

# Every VITE_* is inlined at build time, so they have to arrive as build args.
# A missing one does not fail the build — it compiles to `undefined` and
# surfaces later as a login that never completes.
buildArgs=(--build-arg VITE_API_URL=/api --build-arg VITE_SOCKET_URL=)
while IFS='=' read -r name value; do
    [[ "$name" == VITE_FIREBASE_* || "$name" == VITE_STATUS_CONSTANTS ]] || continue
    buildArgs+=(--build-arg "$name=$value")
done < <(grep -E '^VITE_' noHarm/.env.local)

echo "==> building"
docker build -q -f noHarmBack/docker/Dockerfile -t noharm:latest "${buildArgs[@]}" . >/dev/null

echo "==> shipping $(docker images noharm:latest --format '{{.Size}}')"
docker save noharm:latest | gzip -1 | ssh_ 'gunzip | sudo docker load' | tail -1

echo "==> restarting"
# `up -d` alone would not replace a container whose image tag is unchanged.
ssh_ "cd $REMOTE_DIR && sudo docker compose --env-file prod.env -f compose.host.yaml up -d --force-recreate app"

echo "==> waiting for health"
for _ in $(seq 1 40); do
    if ssh_ 'curl -fs http://127.0.0.1/health' 2>/dev/null; then
        echo
        echo "deployed"
        exit 0
    fi
    sleep 3
done

echo "the app did not become healthy; last 40 log lines:" >&2
ssh_ "cd $REMOTE_DIR && sudo docker compose --env-file prod.env -f compose.host.yaml logs --tail 40 app" >&2
exit 1
