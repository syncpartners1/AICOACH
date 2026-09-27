"""Deploy-config consistency between cloudbuild.yaml and deploy-gcp.yml.

Regression tests for the 2026-09-27 incident: a Cloud Build trigger deployed
main AFTER the GitHub Actions deploy, and its ``--set-env-vars`` (replace
semantics) wiped SMTP_HOST/SMTP_PORT/SMTP_FROM while its ``--set-secrets``
bound SMTP_PASSWORD to the retired SMTP_PASSWORD secret name. The live
revision lost the Brevo SMTP configuration and invite emails stopped
sending. Earlier the same evening, stale EMAILJS_* bindings failed a whole
deploy. These tests keep both pipelines aligned on the email path and free
of removed bindings.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CLOUDBUILD = REPO_ROOT / "cloudbuild.yaml"
DEPLOY_GCP = REPO_ROOT / ".github" / "workflows" / "deploy-gcp.yml"

SMTP_ENV_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM")


def _cloudbuild_main_app():
    """Return (secrets, env_vars) dicts from the cloudbuild deploy-main-app step."""
    steps = yaml.safe_load(CLOUDBUILD.read_text())["steps"]
    step = next(s for s in steps if s.get("id") == "deploy-main-app")
    secrets, env = {}, {}
    for arg in step["args"]:
        for prefix, target in (("--set-secrets=", secrets), ("--set-env-vars=", env)):
            if arg.startswith(prefix):
                for pair in arg[len(prefix):].split(","):
                    key, _, value = pair.partition("=")
                    target[key.strip()] = value.strip()
    return secrets, env


def _actions_main_app():
    """Return (secrets, env_vars) dicts from the deploy-cloudrun step in deploy-gcp.yml."""
    workflow = yaml.safe_load(DEPLOY_GCP.read_text())
    steps = workflow["jobs"]["deploy-main-app"]["steps"]
    step = next(
        s for s in steps
        if str(s.get("uses", "")).startswith("google-github-actions/deploy-cloudrun")
    )
    secrets, env = {}, {}
    for line in step["with"]["secrets"].splitlines():
        key, _, value = line.strip().partition("=")
        if key:
            secrets[key] = value
    for line in step["with"]["env_vars"].splitlines():
        key, _, value = line.strip().partition("=")
        if key:
            env[key] = value
    return secrets, env


def test_no_emailjs_bindings_left_in_deploy_configs():
    for path in (CLOUDBUILD, DEPLOY_GCP):
        assert "EMAILJS" not in path.read_text(), f"EMAILJS binding left in {path.name}"


def test_smtp_password_bound_to_brevo_secret_in_both_pipelines():
    cb_secrets, _ = _cloudbuild_main_app()
    ga_secrets, _ = _actions_main_app()
    assert cb_secrets.get("SMTP_PASSWORD") == "BREVO_SMTP_PASSWORD:latest", (
        "cloudbuild.yaml binds SMTP_PASSWORD to a different secret"
    )
    assert ga_secrets.get("SMTP_PASSWORD") == "BREVO_SMTP_PASSWORD:latest", (
        "deploy-gcp.yml binds SMTP_PASSWORD to a different secret"
    )


def test_smtp_user_binding_aligned():
    cb_secrets, _ = _cloudbuild_main_app()
    ga_secrets, _ = _actions_main_app()
    assert cb_secrets.get("SMTP_USER") == ga_secrets.get("SMTP_USER") == "SMTP_USER:latest"


def test_smtp_env_vars_present_and_identical_in_both_pipelines():
    _, cb_env = _cloudbuild_main_app()
    _, ga_env = _actions_main_app()
    for var in SMTP_ENV_VARS:
        assert var in cb_env, f"{var} missing from cloudbuild.yaml --set-env-vars"
        assert var in ga_env, f"{var} missing from deploy-gcp.yml env_vars"
        assert cb_env[var] == ga_env[var], (
            f"{var} differs: cloudbuild={cb_env[var]!r} actions={ga_env[var]!r}"
        )
