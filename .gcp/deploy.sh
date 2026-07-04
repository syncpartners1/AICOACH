#!/usr/bin/env bash
# =============================================================================
# Change Navigator — Manual Deployment Script
# =============================================================================
# Use this for the FIRST deployment or when you want to deploy manually
# without waiting for GitHub Actions.
#
# Usage:
#   ./.gcp/deploy.sh [main|scheduler|all]
#   ./.gcp/deploy.sh all        # deploys both services (default)
#   ./.gcp/deploy.sh main       # deploys only the main FastAPI app
#   ./.gcp/deploy.sh scheduler  # deploys only the scheduler
# =============================================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-change-navigator-abn}"
REGION="${GCP_REGION:-me-west1}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/change-navigator-docker"
TARGET="${1:-all}"
TAG="manual-$(date +%Y%m%d-%H%M%S)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

echo "=============================================="
echo "  Change Navigator — Manual Deploy"
echo "  Project: ${PROJECT_ID} | Region: ${REGION}"
echo "  Target:  ${TARGET}"
echo "=============================================="

gcloud config set project "${PROJECT_ID}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── Deploy main app ────────────────────────────────────────────────────────────
deploy_main() {
    echo ""
    echo ">>> Building main app image..."
    docker build -t "${REGISTRY}/main-app:${TAG}" -t "${REGISTRY}/main-app:latest" \
        -f "${REPO_ROOT}/Dockerfile" "${REPO_ROOT}"
    docker push "${REGISTRY}/main-app:${TAG}"
    docker push "${REGISTRY}/main-app:latest"

    echo ">>> Deploying change-navigator to Cloud Run..."
    gcloud run deploy change-navigator \
        --image="${REGISTRY}/main-app:${TAG}" \
        --region="${REGION}" \
        --platform=managed \
        --allow-unauthenticated \
        --memory=512Mi \
        --cpu=1 \
        --min-instances=0 \
        --max-instances=10 \
        --concurrency=80 \
        --timeout=300 \
        --service-account="main-app-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --set-secrets="\
ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,\
COACHING_API_KEY=COACHING_API_KEY:latest,\
SUPABASE_URL=SUPABASE_URL:latest,\
SUPABASE_SERVICE_KEY=SUPABASE_SERVICE_KEY:latest,\
TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
TELEGRAM_BOT_USERNAME=TELEGRAM_BOT_USERNAME:latest,\
ADMIN_TELEGRAM_ID=ADMIN_TELEGRAM_ID:latest,\
WHATSAPP_ACCESS_TOKEN=WHATSAPP_ACCESS_TOKEN:latest,\
WHATSAPP_PHONE_NUMBER_ID=WHATSAPP_PHONE_NUMBER_ID:latest,\
WHATSAPP_BUSINESS_ACCOUNT_ID=WHATSAPP_BUSINESS_ACCOUNT_ID:latest,\
WHATSAPP_APP_SECRET=WHATSAPP_APP_SECRET:latest,\
WHATSAPP_VERIFY_TOKEN=WHATSAPP_VERIFY_TOKEN:latest,\
GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,\
GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,\
GOOGLE_REDIRECT_URI=GOOGLE_REDIRECT_URI:latest,\
FACEBOOK_APP_ID=FACEBOOK_APP_ID:latest,\
FACEBOOK_APP_SECRET=FACEBOOK_APP_SECRET:latest,\
ADMIN_FACEBOOK_ID=ADMIN_FACEBOOK_ID:latest,\
ADMIN_PASSWORD=ADMIN_PASSWORD:latest,\
ADMIN_USER_ID=ADMIN_USER_ID:latest,\
ADMIN_USERNAME=ADMIN_USERNAME:latest,\
ADMIN_WHATSAPP_PHONE=ADMIN_WHATSAPP_PHONE:latest,\
SCHEDULER_URL=SCHEDULER_URL:latest,\
SCHEDULER_API_KEY=SCHEDULER_API_KEY:latest,\
EMAILJS_SERVICE_ID=EMAILJS_SERVICE_ID:latest,\
EMAILJS_TEMPLATE_INVITE=EMAILJS_TEMPLATE_INVITE:latest,\
EMAILJS_TEMPLATE_WELCOME=EMAILJS_TEMPLATE_WELCOME:latest,\
EMAILJS_PUBLIC_KEY=EMAILJS_PUBLIC_KEY:latest,\
EMAILJS_PRIVATE_KEY=EMAILJS_PRIVATE_KEY:latest,\
COACHING_DEMO_KEY=COACHING_DEMO_KEY:latest" \
        --set-env-vars="\
TELEGRAM_WEBHOOK_MODE=true,\
COACHING_LLM_MODEL=claude-haiku-4-5-20251001,\
COACHING_LLM_TEMPERATURE=0.7,\
SCHEDULER_TIMEZONE=Asia/Jerusalem,\
GCP_PROJECT_ID=${PROJECT_ID}" \
        --project="${PROJECT_ID}"

    # Get the deployed URL
    MAIN_URL=$(gcloud run services describe change-navigator \
        --region="${REGION}" --project="${PROJECT_ID}" \
        --format="value(status.url)")
    echo ""
    echo "✅ Main app deployed: ${MAIN_URL}"

    # Update PUBLIC_URL secret so the app knows its own URL
    echo -n "${MAIN_URL}" | gcloud secrets versions add "PUBLIC_URL" \
        --data-file=- --project="${PROJECT_ID}" --quiet 2>/dev/null || \
    echo -n "${MAIN_URL}" | gcloud secrets create "PUBLIC_URL" \
        --data-file=- --replication-policy=automatic --project="${PROJECT_ID}" --quiet

    # Re-deploy with updated PUBLIC_URL (webhook registration needs this)
    gcloud run services update change-navigator \
        --region="${REGION}" \
        --update-secrets="PUBLIC_URL=PUBLIC_URL:latest" \
        --project="${PROJECT_ID}" --quiet

    echo ""
    echo "  Next: Update Google OAuth redirect URI to: ${MAIN_URL}/auth/google/callback"
    echo "  Next: Update WhatsApp webhook to: ${MAIN_URL}/whatsapp/webhook"
}

# ── Deploy scheduler ──────────────────────────────────────────────────────────
deploy_scheduler() {
    echo ""
    echo ">>> Building scheduler image..."
    docker build -t "${REGISTRY}/scheduler:${TAG}" -t "${REGISTRY}/scheduler:latest" \
        "${REPO_ROOT}/scheduler"
    docker push "${REGISTRY}/scheduler:${TAG}"
    docker push "${REGISTRY}/scheduler:latest"

    echo ">>> Deploying change-navigator-scheduler to Cloud Run..."
    gcloud run deploy change-navigator-scheduler \
        --image="${REGISTRY}/scheduler:${TAG}" \
        --region="${REGION}" \
        --platform=managed \
        --no-allow-unauthenticated \
        --memory=256Mi \
        --cpu=1 \
        --min-instances=0 \
        --max-instances=5 \
        --concurrency=100 \
        --timeout=30 \
        --service-account="scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --set-secrets="\
SCHEDULER_API_KEY=SCHEDULER_API_KEY:latest,\
GOOGLE_SERVICE_ACCOUNT_JSON=GOOGLE_SERVICE_ACCOUNT_JSON:latest,\
CALENDAR_ID=CALENDAR_ID:latest" \
        --set-env-vars="\
SCHEDULER_TIMEZONE=Asia/Jerusalem,\
WORKING_HOURS_START=09:00,\
WORKING_HOURS_END=18:00,\
NODE_ENV=production" \
        --project="${PROJECT_ID}"

    # Get deployed URL
    SCHEDULER_URL=$(gcloud run services describe change-navigator-scheduler \
        --region="${REGION}" --project="${PROJECT_ID}" \
        --format="value(status.url)")

    echo ""
    echo "✅ Scheduler deployed: ${SCHEDULER_URL}"
    echo ""
    echo "  Update SCHEDULER_URL secret in main app:"
    echo -n "${SCHEDULER_URL}" | gcloud secrets versions add "SCHEDULER_URL" \
        --data-file=- --project="${PROJECT_ID}" --quiet 2>/dev/null || \
    echo -n "${SCHEDULER_URL}" | gcloud secrets create "SCHEDULER_URL" \
        --data-file=- --replication-policy=automatic --project="${PROJECT_ID}" --quiet
    echo "  ✅ SCHEDULER_URL secret updated to ${SCHEDULER_URL}"

    # Grant main app service account permission to invoke scheduler (internal auth)
    gcloud run services add-iam-policy-binding change-navigator-scheduler \
        --member="serviceAccount:main-app-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/run.invoker" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" --quiet || true
}

# ── Run selected target ────────────────────────────────────────────────────────
case "$TARGET" in
    main)       deploy_main ;;
    scheduler)  deploy_scheduler ;;
    all)
        deploy_scheduler
        deploy_main
        ;;
    *)
        echo "Usage: $0 [main|scheduler|all]"
        exit 1
        ;;
esac

echo ""
echo "=============================================="
echo "  Deployment complete!"
echo "=============================================="
