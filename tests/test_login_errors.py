"""The /login page explains an unlinked Google account and never reflects raw query text."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app

client = TestClient(app)


def test_recovery_required_explains_and_links_to_identity_link():
    r = client.get("/login?error=recovery_required")
    assert r.status_code == 200
    assert "not linked to a coaching profile yet" in r.text and "Link it here" in r.text
    assert 'href="/identity/link"' in r.text
    assert "/google" in r.text and "Please try again" not in r.text.split("error-banner")[1].split("</div>")[0]


def test_other_google_reasons_have_plain_messages():
    for code, text in (("invalid_state", "expired or was opened in a different browser"),
                       ("account_inactive", "not active"), ("cancelled", "cancelled")):
        banner = client.get("/login?error=" + code).text.split('class="error-banner">')[1].split("</div>")[0]
        assert text in banner and "Sign-in failed (" not in banner


def test_unknown_error_text_is_escaped():
    r = client.get('/login?error=%3Cscript%3Ealert(1)%3C/script%3E')
    assert "<script>alert(1)" not in r.text
    assert "&lt;script&gt;" in r.text


def test_no_error_shows_no_banner():
    assert 'class="error-banner">' not in client.get("/login").text
