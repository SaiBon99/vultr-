#!/usr/bin/env bash
# Prepare a VM for POST /crawl (D7): install Docker if missing, make sure the daemon runs, let the
# service user run Docker, and build the crawler sandbox image from backend/sandbox.
# Idempotent: a second run on a prepared machine changes nothing and exits 0.
# Never reads, prints or copies any .env file or key. The image name comes from --image, else the
# CRAWL_SANDBOX_IMAGE environment variable, else the backend default.
#
# Usage: setup_crawl_sandbox.sh [--user NAME] [--image NAME:TAG] [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTEXT="$REPO_ROOT/backend/sandbox"
IMAGE="${CRAWL_SANDBOX_IMAGE:-memory-quarantine-crawler:latest}"
RUN_USER="${SUDO_USER:-$USER}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --user) RUN_USER="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ $*" >&2
  else
    "$@"
  fi
}

echo "== Docker"
if command -v docker >/dev/null 2>&1; then
  echo "ok: $(docker --version)"
else
  echo "Docker is missing; installing docker.io"
  run $SUDO apt-get update -y
  run $SUDO apt-get install -y docker.io
fi

echo "== Docker daemon"
# Use plain docker when this shell can already reach the daemon; sudo only when it cannot.
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  DOCKER="$SUDO docker"
fi
if [ "$DRY_RUN" -eq 0 ] && $DOCKER info >/dev/null 2>&1; then
  echo "ok: daemon is running"
else
  run $SUDO systemctl enable --now docker
  if [ "$DRY_RUN" -eq 0 ] && ! $DOCKER info >/dev/null 2>&1; then
    echo "FAIL: the Docker daemon is not running (check: systemctl status docker)" >&2
    exit 1
  fi
fi

echo "== docker group for $RUN_USER"
if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "FAIL: user $RUN_USER does not exist" >&2
  exit 1
fi
if id -nG "$RUN_USER" | tr ' ' '\n' | grep -qx docker; then
  echo "ok: $RUN_USER is already in the docker group"
else
  run $SUDO usermod -aG docker "$RUN_USER"
  echo "added $RUN_USER to the docker group (takes effect on the next login or service restart)"
fi
echo "WARNING: members of the docker group are effectively root on this VM (accepted known risk, D7)."

echo "== sandbox image $IMAGE"
if [ ! -f "$CONTEXT/Dockerfile" ]; then
  echo "FAIL: $CONTEXT/Dockerfile not found" >&2
  exit 1
fi
# Attestations carry a timestamp, which would give every rebuild a new image id; the legacy
# builder (no buildx) has none and rejects the flags.
BUILD_FLAGS=()
if $DOCKER buildx version >/dev/null 2>&1; then
  BUILD_FLAGS=(--provenance=false --sbom=false)
fi
run $DOCKER build --quiet "${BUILD_FLAGS[@]}" --tag "$IMAGE" "$CONTEXT" >/dev/null
if [ "$DRY_RUN" -eq 0 ]; then
  echo "image $IMAGE id $($DOCKER image inspect --format '{{.Id}}' "$IMAGE")"
fi
echo "done"
