"""Runtime must not fall back to the retired Supabase service or database."""
from unittest.mock import patch

import pytest

from autogpt.coaching import db, storage
from autogpt.coaching.config import coaching_config


def test_storage_uses_cloud_sql_even_with_old_supabase_env(monkeypatch):
    monkeypatch.setattr(coaching_config, 'database_url', 'postgresql://cloudsql/db')
    monkeypatch.setenv('SUPABASE_URL', 'https://old.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'do-not-use')
    with patch.object(db, 'PGClient') as client:
        storage._get_client()
        client.assert_called_once_with()
    assert db.get_db_url() == 'postgresql://cloudsql/db'


def test_missing_database_url_fails_closed_not_supabase(monkeypatch):
    monkeypatch.setattr(coaching_config, 'database_url', '')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('SUPABASE_URL', 'https://old.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'do-not-use')
    assert db.get_db_url() == ''
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        storage._get_client()


def test_database_url_from_runtime_env_still_supported(monkeypatch):
    monkeypatch.setattr(coaching_config, 'database_url', '')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://cloudsql/from-env')
    assert db.get_db_url() == 'postgresql://cloudsql/from-env'


def test_cloudbuild_no_longer_binds_supabase_secrets():
    from pathlib import Path
    content = (Path(__file__).resolve().parents[1] / 'cloudbuild.yaml').read_text()
    assert 'SUPABASE_URL=' not in content
    assert 'SUPABASE_SERVICE_KEY=' not in content
    assert 'DATABASE_URL=DATABASE_URL:latest' in content


def test_github_main_deploy_removes_only_supabase_inherited_bindings():
    from pathlib import Path
    content = (Path(__file__).resolve().parents[1] / '.github/workflows/deploy-gcp.yml').read_text()
    assert '--remove-secrets=SUPABASE_URL,SUPABASE_SERVICE_KEY' in content
    assert 'DATABASE_URL=DATABASE_URL:latest' in content
    assert 'SMTP_PASSWORD=BREVO_SMTP_PASSWORD:latest' in content
    assert '--clear-secrets' not in content
    assert 'secrets_update_strategy: overwrite' not in content
