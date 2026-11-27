#!/usr/bin/env bash
# Provision Vultr resources: Managed PostgreSQL (pgvector), Object Storage, VX1 instance.
# DRY-RUN by default: prints the commands. Pass --apply to run them (creates BILLABLE resources).
# Needs vultr-cli and VULTR_API_KEY. Plan ids and region are placeholders: check `vultr-cli database plans`,
# `vultr-cli object-storage clusters`, `vultr-cli instance list` options before applying.
set -euo pipefail

APPLY=0
REGION="${VULTR_REGION:-ewr}"
DB_PLAN="${VULTR_DB_PLAN:-vultr-dbaas-startup-cc-1-55-2}"
VX1_PLAN="${VULTR_VX1_PLAN:-REPLACE_WITH_VX1_PLAN}"
OS_ID="${VULTR_OS_ID:-2284}"   # Ubuntu 24.04 LTS x64; verify with `vultr-cli os list`
OBJ_CLUSTER="${VULTR_OBJ_CLUSTER_ID:-REPLACE_WITH_CLUSTER_ID}"
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

run() {
  if [ "$APPLY" -eq 1 ]; then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi
}

if [ "$APPLY" -eq 1 ]; then
  command -v vultr-cli >/dev/null || { echo "vultr-cli not found" >&2; exit 1; }
  : "${VULTR_API_KEY:?VULTR_API_KEY must be set}"
  export VULTR_API_KEY
else
  echo "DRY RUN (nothing is created). Re-run with --apply to act."
fi

echo "== Managed PostgreSQL (16). Then enable pgvector: CREATE EXTENSION vector (apply_sql.py does this)."
run vultr-cli database create --database-engine pg --database-engine-version 16 \
  --region "$REGION" --plan "$DB_PLAN" --label quarantine-pg

echo "== Object Storage (S3). Bucket quarantine-receipts is created by the app/smoke tooling via S3 API."
run vultr-cli object-storage create --cluster-id "$OBJ_CLUSTER" --label quarantine-receipts

echo "== VX1 instance (Ubuntu 24.04), then run setup_vultr_vx1.sh on it"
run vultr-cli instance create --region "$REGION" --plan "$VX1_PLAN" --os "$OS_ID" --label quarantine-vx1

echo "Next: copy connection details into infra/.env, then run apply_sql.py and smoke_check.py."
