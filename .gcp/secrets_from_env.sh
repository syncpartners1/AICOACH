#!/usr/bin/env bash
# =============================================================================
# Change Navigator — Migrate .env → GCP Secret Manager
# =============================================================================
# Reads a local .env file and creates/updates each variable as a Secret Manager
# secret. Variables with empty values are skipped.
#
# Usage:
#   ./.gcp/secrets_from_env.sh              # reads .env in current dir
#   ENV_FILE=.env.local .gcp/secrets_from_env.sh
# =============================================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-change-navigator-abn}"
ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "${ENV_FILE}" ]; then
    echo "❌ ${ENV_FILE} not found. Create it from .env.template first."
    exit 1
fi

echo "Uploading secrets from ${ENV_FILE} to GCP Secret Manager (project: ${PROJECT_ID})..."
echo ""

# Variables to SKIP (not secrets — set as plain env vars in Cloud Run instead)
SKIP_VARS=(
    "PORT"
    "NODE_ENV"
    "SCHEDULER_TIMEZONE"
    "WORKING_HOURS_START"
    "WORKING_HOURS_END"
    "COACHING_LLM_MODEL"
    "COACHING_LLM_TEMPERATURE"
    "COACHING_COACH_NAME"
    "COACHING_ALERT_RED_THRESHOLD"
    "COACHING_ALERT_YELLOW_THRESHOLD"
    "TELEGRAM_WEBHOOK_MODE"
    "GCP_PROJECT_ID"
    "GCP_REGION"
)

SUCCESS=0
SKIPPED=0
FAILED=0

# Parse .env file: skip comments and blank lines
while IFS= read -r line || [ -n "$line" ]; do
    line="${line//$'\r'/}"
    # Skip comments and blank lines
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    # Skip lines without =
    [[ "$line" != *"="* ]] && continue

    KEY="${line%%=*}"
    VALUE="${line#*=}"
    # Strip surrounding quotes from value
    VALUE="${VALUE%\"}"
    VALUE="${VALUE#\"}"
    VALUE="${VALUE%\'}"
    VALUE="${VALUE#\'}"
    KEY="${KEY//[[:space:]]/}"  # strip whitespace from key

    # Skip empty keys or empty values
    [ -z "$KEY" ] || [ -z "$VALUE" ] && { ((SKIPPED++)) || true; continue; }

    # Skip non-secret vars
    SHOULD_SKIP=false
    for SKIP in "${SKIP_VARS[@]}"; do
        if [ "$KEY" = "$SKIP" ]; then
            SHOULD_SKIP=true
            break
        fi
    done
    if $SHOULD_SKIP; then
        echo "  ⏭  Skipping (plain env var): $KEY"
        ((SKIPPED++)) || true
        continue
    fi

    # Create or update secret
    if gcloud secrets describe "$KEY" --project="$PROJECT_ID" &>/dev/null; then
        # Secret exists — add new version
        echo -n "$VALUE" | gcloud secrets versions add "$KEY" \
            --data-file=- --project="$PROJECT_ID" --quiet
        echo "  ✅ Updated: $KEY"
    else
        # Create new secret
        echo -n "$VALUE" | gcloud secrets create "$KEY" \
            --data-file=- \
            --replication-policy=automatic \
            --project="$PROJECT_ID" --quiet
        echo "  ✅ Created: $KEY"
    fi
    ((SUCCESS++)) || true

done < "${ENV_FILE}"

echo ""
echo "Done. ${SUCCESS} secrets uploaded, ${SKIPPED} skipped, ${FAILED} failed."
echo ""
echo "Grant access to service accounts if not done in setup.sh:"
echo "  gcloud projects add-iam-policy-binding ${PROJECT_ID} \\"
echo "    --member=serviceAccount:main-app-sa@${PROJECT_ID}.iam.gserviceaccount.com \\"
echo "    --role=roles/secretmanager.secretAccessor"
