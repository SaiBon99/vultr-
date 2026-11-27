#!/usr/bin/env bash
# Provision Vultr resources: Managed PostgreSQL (pgvector), Object Storage, VX1 instance.
# DRY-RUN by default: prints the commands. Pass --apply to run them (creates BILLABLE resources).
# Needs vultr-cli (flags checked against v3.11.0 help) and VULTR_API_KEY. Plan ids are placeholders: check
# `vultr-cli database plans` and `vultr-cli plans list` before applying. The Object Storage cluster and tier
# are looked up (read-only, also in dry run when vultr-cli and VULTR_API_KEY are present); override with
# VULTR_OBJ_CLUSTER_ID / VULTR_OBJ_TIER_ID.
set -euo pipefail

APPLY=0
REGION="${VULTR_REGION:-ewr}"
DB_PLAN="${VULTR_DB_PLAN:-vultr-dbaas-startup-cc-1-55-2}"
VX1_PLAN="${VULTR_VX1_PLAN:-REPLACE_WITH_VX1_PLAN}"
OS_ID="${VULTR_OS_ID:-2284}"   # Ubuntu 24.04 LTS x64; verify with `vultr-cli os list`
OBJ_CLUSTER="${VULTR_OBJ_CLUSTER_ID:-}"
OBJ_TIER="${VULTR_OBJ_TIER_ID:-}"
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

echo "== Object Storage (S3). Receipts and run logs (logs/) share one bucket, created by setup_object_storage.py."
# Read-only lookup: the deployable cluster in $REGION, then its default tier (create needs both).
can_lookup=0
if command -v vultr-cli >/dev/null && command -v jq >/dev/null && [ -n "${VULTR_API_KEY:-}" ]; then
  export VULTR_API_KEY
  can_lookup=1
fi
OBJ_HOST=""
if [ -z "$OBJ_CLUSTER" ]; then
  if [ "$can_lookup" -eq 1 ]; then
    clusters="$(vultr-cli object-storage cluster list -o json)"
    OBJ_CLUSTER="$(jq -r --arg r "$REGION" \
      '[.clusters[] | select(.region == $r and .deploy == "yes")][0].id // empty' <<<"$clusters")"
    if [ -z "$OBJ_CLUSTER" ]; then
      echo "no deployable Object Storage cluster in region '$REGION'. Available:" >&2
      jq -r '.clusters[] | "  id=\(.id) region=\(.region) host=\(.hostname) deploy=\(.deploy)"' <<<"$clusters" >&2
      exit 1
    fi
    OBJ_HOST="$(jq -r --argjson id "$OBJ_CLUSTER" '.clusters[] | select(.id == $id) | .hostname' <<<"$clusters")"
    echo "cluster: id=$OBJ_CLUSTER region=$REGION host=$OBJ_HOST"
  elif [ "$APPLY" -eq 1 ]; then
    echo "cluster lookup needs vultr-cli, jq and VULTR_API_KEY (or set VULTR_OBJ_CLUSTER_ID)" >&2; exit 1
  else
    echo "[dry-run] vultr-cli object-storage cluster list -o json  # pick region == $REGION, deploy == yes"
    OBJ_CLUSTER='<cluster-id>'
  fi
fi
if [ -z "$OBJ_TIER" ]; then
  if [ "$can_lookup" -eq 1 ] && [ "$OBJ_CLUSTER" != '<cluster-id>' ]; then
    OBJ_TIER="$(vultr-cli object-storage cluster tiers --cluster-id "$OBJ_CLUSTER" -o json \
      | jq -r '(([.tiers[] | select(.is_default == "yes")] + .tiers)[0].id) // empty')"
    [ -n "$OBJ_TIER" ] || { echo "no Object Storage tier for cluster $OBJ_CLUSTER" >&2; exit 1; }
    echo "tier: id=$OBJ_TIER"
  else
    echo "[dry-run] vultr-cli object-storage cluster tiers --cluster-id $OBJ_CLUSTER -o json  # default tier"
    OBJ_TIER='<tier-id>'
  fi
fi
OBJ_REGION_ID="${OBJ_HOST%%.*}"; OBJ_REGION_ID="${OBJ_REGION_ID:-ewr1}"
run vultr-cli object-storage create --cluster-id "$OBJ_CLUSTER" --tier-id "$OBJ_TIER" --label quarantine-receipts
echo "Next (Object Storage): \`vultr-cli object-storage list\` for the subscription id, then"
echo "  \`vultr-cli object-storage get <id>\` shows the S3 hostname and keys. In the VM env file set"
echo "  S3_ENDPOINT_URL=https://<s3_hostname>, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION=<hostname prefix, e.g. ${OBJ_REGION_ID}>"
echo "  and a cluster-unique S3_BUCKET, then run setup_object_storage.py. Do not paste keys into logs or chat."

echo "== VX1 instance (Ubuntu 24.04), then run setup_vultr_vx1.sh on it"
run vultr-cli instance create --region "$REGION" --plan "$VX1_PLAN" --os "$OS_ID" --label quarantine-vx1

echo "Next: copy connection details into infra/.env, then run apply_sql.py and smoke_check.py."
