#!/usr/bin/env bash
# =============================================================================
# Change Navigator — GCP One-Shot Setup Script
# =============================================================================
# Run this ONCE to bootstrap the entire GCP infrastructure.
# It is idempotent: safe to re-run if interrupted.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - A billing account linked to the project (or use free trial credits)
#
# Usage:
#   chmod +x .gcp/setup.sh
#   ./.gcp/setup.sh
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-change-navigator-abn}"
REGION="${GCP_REGION:-me-west1}"
REGISTRY_NAME="change-navigator-docker"
MAIN_SERVICE="change-navigator"
SCHEDULER_SERVICE="change-navigator-scheduler"
MAIN_SA="main-app-sa"
SCHEDULER_SA="scheduler-sa"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"  # Set this or link manually in console

echo "=============================================="
echo "  Change Navigator — GCP Setup"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "=============================================="

# ── 1. Create or select project ───────────────────────────────────────────────
echo ""
echo "[1/8] Creating/selecting project..."
if gcloud projects describe "${PROJECT_ID}" &>/dev/null; then
    echo "  → Project ${PROJECT_ID} already exists, selecting it."
else
    gcloud projects create "${PROJECT_ID}" --name="Change Navigator"
    echo "  → Project ${PROJECT_ID} created."
fi
gcloud config set project "${PROJECT_ID}"

# Link billing account if provided
if [ -n "${BILLING_ACCOUNT}" ]; then
    gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT}"
    echo "  → Billing account linked."
else
    echo "  ⚠️  No BILLING_ACCOUNT set. Link billing manually:"
    echo "     https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}"
fi

# ── 2. Enable required APIs ───────────────────────────────────────────────────
echo ""
echo "[2/8] Enabling GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    iamcredentials.googleapis.com \
    --project="${PROJECT_ID}"
echo "  → APIs enabled."

# ── 3. Create Artifact Registry repository ────────────────────────────────────
echo ""
echo "[3/8] Creating Artifact Registry repository..."
if gcloud artifacts repositories describe "${REGISTRY_NAME}" \
    --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  → Repository already exists."
else
    gcloud artifacts repositories create "${REGISTRY_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Docker images for Change Navigator services" \
        --project="${PROJECT_ID}"
    echo "  → Repository created: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REGISTRY_NAME}"
fi

# ── 4. Create service accounts ────────────────────────────────────────────────
echo ""
echo "[4/8] Creating service accounts..."

# Main app service account
if gcloud iam service-accounts describe "${MAIN_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="${PROJECT_ID}" &>/dev/null; then
    echo "  → ${MAIN_SA} already exists."
else
    gcloud iam service-accounts create "${MAIN_SA}" \
        --display-name="Change Navigator Main App" \
        --project="${PROJECT_ID}"
    echo "  → Created service account: ${MAIN_SA}"
fi

# Scheduler service account
if gcloud iam service-accounts describe "${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="${PROJECT_ID}" &>/dev/null; then
    echo "  → ${SCHEDULER_SA} already exists."
else
    gcloud iam service-accounts create "${SCHEDULER_SA}" \
        --display-name="Change Navigator Scheduler" \
        --project="${PROJECT_ID}"
    echo "  → Created service account: ${SCHEDULER_SA}"
fi

# ── 5. Grant IAM roles ────────────────────────────────────────────────────────
echo ""
echo "[5/8] Assigning IAM roles..."

# Main app: Secret Manager accessor
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${MAIN_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None --quiet

# Scheduler: Secret Manager accessor
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None --quiet

# Cloud Build service account: Cloud Run deployer + Artifact Registry writer
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/run.admin" \
    --condition=None --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/artifactregistry.writer" \
    --condition=None --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/iam.serviceAccountUser" \
    --condition=None --quiet

echo "  → IAM roles assigned."

# ── 6. Create Google Calendar service account key (for scheduler) ─────────────
echo ""
echo "[6/8] Setting up Google Calendar access for scheduler..."
echo "  → Creating Google Calendar service account key..."
KEY_FILE=".gcp/scheduler-calendar-key.json"
if [ -f "${KEY_FILE}" ]; then
    echo "  → Key file already exists at ${KEY_FILE}, skipping."
else
    gcloud iam service-accounts keys create "${KEY_FILE}" \
        --iam-account="${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --project="${PROJECT_ID}"
    echo "  → Key saved to ${KEY_FILE}"
    echo ""
    echo "  ⚠️  IMPORTANT: You must share your Google Calendar with this service account:"
    echo "     Email: ${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
    echo "     Permission: 'Make changes to events'"
    echo "     In Google Calendar: Settings > [Your Calendar] > Share with specific people"
fi

# ── 7. Upload secrets ─────────────────────────────────────────────────────────
echo ""
echo "[7/8] Uploading secrets to Secret Manager..."
echo "  → Running secrets_from_env.sh..."
if [ -f ".env" ]; then
    bash .gcp/secrets_from_env.sh
else
    echo "  ⚠️  No .env file found. Run .gcp/secrets_from_env.sh manually after creating .env"
fi

# Upload scheduler calendar key as a secret
if [ -f "${KEY_FILE}" ]; then
    if gcloud secrets describe "GOOGLE_SERVICE_ACCOUNT_JSON" --project="${PROJECT_ID}" &>/dev/null; then
        echo "  → GOOGLE_SERVICE_ACCOUNT_JSON secret already exists."
    else
        gcloud secrets create "GOOGLE_SERVICE_ACCOUNT_JSON" \
            --data-file="${KEY_FILE}" \
            --project="${PROJECT_ID}"
        echo "  → Uploaded GOOGLE_SERVICE_ACCOUNT_JSON to Secret Manager."
    fi
fi

# ── 8. Set up Workload Identity Federation for GitHub Actions ─────────────────
echo ""
echo "[8/8] Setting up Workload Identity Federation (GitHub Actions)..."
WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"
GITHUB_REPO="${GITHUB_REPO:-}"  # e.g. "myorg/AICOACH"

if gcloud iam workload-identity-pools describe "${WIF_POOL}" \
    --location=global --project="${PROJECT_ID}" &>/dev/null; then
    echo "  → Workload Identity Pool already exists."
else
    gcloud iam workload-identity-pools create "${WIF_POOL}" \
        --location=global \
        --display-name="GitHub Actions Pool" \
        --project="${PROJECT_ID}"
    echo "  → Created Workload Identity Pool: ${WIF_POOL}"
fi

if gcloud iam workload-identity-pools providers describe "${WIF_PROVIDER}" \
    --workload-identity-pool="${WIF_POOL}" \
    --location=global --project="${PROJECT_ID}" &>/dev/null; then
    echo "  → Workload Identity Provider already exists."
else
    gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
        --workload-identity-pool="${WIF_POOL}" \
        --location=global \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
        --attribute-condition="assertion.repository_owner == '$(echo ${GITHUB_REPO} | cut -d/ -f1)'" \
        --project="${PROJECT_ID}"
    echo "  → Created Workload Identity Provider: ${WIF_PROVIDER}"
fi

# Allow GitHub Actions to impersonate the main app service account
if [ -n "${GITHUB_REPO}" ]; then
    WIF_PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}"
    gcloud iam service-accounts add-iam-policy-binding \
        "${MAIN_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --member="${WIF_PRINCIPAL}" \
        --role="roles/iam.workloadIdentityUser" \
        --project="${PROJECT_ID}" --quiet
    echo "  → GitHub repo ${GITHUB_REPO} can now impersonate ${MAIN_SA}"
else
    echo "  ⚠️  Set GITHUB_REPO=owner/repo-name to complete WIF setup."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Add billing if not done: https://console.cloud.google.com/billing"
echo "  2. Share Google Calendar with: ${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "  3. Run: .gcp/secrets_from_env.sh (if not done above)"
echo "  4. Run: .gcp/deploy.sh to build and deploy both services"
echo "=============================================="
