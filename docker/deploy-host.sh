#!/usr/bin/env bash
# Build here, ship the image, restart there.
#
# Run from the directory that holds BOTH repos — noHarm/ and noHarmBack/ — the
# same context the Dockerfile needs, because stage 1 compiles the front-end.
#
#   ./noHarmBack/docker/deploy-host.sh              # deploy + release
#   ./noHarmBack/docker/deploy-host.sh --no-release # deploy only (hotfix)
#
# A release is a version number and its notes. The script asks for both
# before building, deploys, and only once the server is healthy tags BOTH
# repos `vX.Y.Z` (an annotated tag carrying the notes) and pushes the tags.
# The tag push is what starts noHarm's `release` workflow, which builds the
# signed Android APK and publishes the GitHub Release with it — see
# noHarm/.github/workflows/release.yml. A deploy that fails tags nothing.
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

# The Elastic IP, not the ec2-*.compute-1.amazonaws.com name: that hostname
# encodes the address it was issued for, so it dies the moment the instance
# gets a different one. An Elastic IP is the thing that does not move.
HOST="${NOHARM_HOST:-ec2-user@34.225.81.236}"
KEY="${NOHARM_SSH_KEY:-noharm-ssh.pem}"
REMOTE_DIR="~/noHarmBack/docker"

[[ -d noHarm && -d noHarmBack ]] || {
    echo "run this from the directory containing noHarm/ and noHarmBack/" >&2
    exit 1
}
[[ -r "$KEY" ]] || { echo "ssh key not readable at $KEY" >&2; exit 1; }

ssh_() { ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST" "$@"; }

# ── Release: version and notes, asked for before anything is built ─────────
RELEASE=1
[[ "${1:-}" == "--no-release" ]] && RELEASE=0
VERSION=""
NOTES_FILE=""

latestTag() {
    git -C "$1" tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1
}

if (( RELEASE )); then
    for repo in noHarm noHarmBack; do
        # A tag has to name a commit the workflow can check out, and the code
        # it names has to be the code that was deployed: no uncommitted work,
        # nothing that is only on this machine.
        if [[ -n "$(git -C "$repo" status --porcelain)" ]]; then
            echo "$repo has uncommitted changes — commit them, or deploy with --no-release" >&2
            exit 1
        fi
        git -C "$repo" fetch --quiet --tags origin
        if [[ -z "$(git -C "$repo" branch -r --contains HEAD)" ]]; then
            echo "$repo: HEAD is not pushed — push it, or deploy with --no-release" >&2
            exit 1
        fi
    done

    last="$(latestTag noHarm)"
    if [[ -n "$last" ]]; then
        IFS=. read -r major minor patch <<<"${last#v}"
        suggestion="v$major.$minor.$((patch + 1))"
    else
        suggestion="v1.0.0"
    fi

    while :; do
        read -rp "release tag [${suggestion}] (last: ${last:-none}): " VERSION
        VERSION="${VERSION:-$suggestion}"
        [[ "$VERSION" == v* ]] || VERSION="v$VERSION"
        if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "  use vMAJOR.MINOR.PATCH, e.g. v1.2.3"; continue
        fi
        if git -C noHarm rev-parse -q --verify "refs/tags/$VERSION" >/dev/null \
            || git -C noHarmBack rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
            echo "  $VERSION already exists"; continue
        fi
        if [[ -n "$last" && "$(printf '%s\n%s\n' "$last" "$VERSION" | sort -V | tail -1)" != "$VERSION" ]]; then
            echo "  $VERSION is not newer than $last"; continue
        fi
        break
    done

    # Notes in the editor git already uses, like a commit message: lines
    # starting with # are dropped, and an empty result aborts.
    NOTES_FILE="$(mktemp)"
    trap 'rm -f "$NOTES_FILE"' EXIT
    {
        echo
        echo "# Release notes for $VERSION — what changed, for the people using the app."
        echo "# Lines starting with # are ignored. Leave it empty to abort."
        echo "#"
        echo "# noHarm since ${last:-the beginning}:"
        git -C noHarm log --format='#   %s' ${last:+"$last"..HEAD} | head -30
        echo "# noHarmBack since ${last:-the beginning}:"
        git -C noHarmBack log --format='#   %s' ${last:+"$last"..HEAD} 2>/dev/null | head -30
    } >"$NOTES_FILE"
    editor="$(git var GIT_EDITOR)"
    eval "$editor \"\$NOTES_FILE\""
    sed -i '/^#/d' "$NOTES_FILE"
    if [[ -z "$(tr -d '[:space:]' <"$NOTES_FILE")" ]]; then
        echo "empty release notes — aborted, nothing was deployed" >&2
        exit 1
    fi
    echo "==> releasing $VERSION after the deploy"
fi

# Every VITE_* is inlined at build time, so they have to arrive as build args.
# A missing one does not fail the build — it compiles to `undefined` and
# surfaces later as a login that never completes.
buildArgs=(--build-arg VITE_API_URL=/api --build-arg VITE_SOCKET_URL=)
# Shown in Settings. A deploy without a release is still told apart from one.
buildArgs+=(--build-arg "VITE_APP_VERSION=${VERSION:-$(git -C noHarm describe --tags --always --dirty)}")
while IFS='=' read -r name value; do
    case "$name" in
        VITE_FIREBASE_*|VITE_STATUS_CONSTANTS) ;;
        VITE_DELETION_GRACE_DAYS|VITE_MINIMUM_AGE|VITE_SUPPORT_EMAIL) ;;
        *) continue ;;
    esac
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
        if (( RELEASE )); then
            # Both repos get the same tag: the version names the pair that was
            # deployed together. The tag on noHarm starts the release workflow.
            for repo in noHarmBack noHarm; do
                git -C "$repo" tag -a "$VERSION" -F "$NOTES_FILE"
                git -C "$repo" push --quiet origin "refs/tags/$VERSION"
            done
            echo "==> tagged $VERSION in both repos"
            echo "    the APK and the Release: https://github.com/LeoGotardo/noHarm/actions/workflows/release.yml"
        fi
        exit 0
    fi
    sleep 3
done

echo "the app did not become healthy; last 40 log lines:" >&2
ssh_ "cd $REMOTE_DIR && sudo docker compose --env-file prod.env -f compose.host.yaml logs --tail 40 app" >&2
exit 1
