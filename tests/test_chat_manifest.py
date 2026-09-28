"""Phase 7.1 install metadata; private chat content remains cookie-gated."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app
from autogpt.coaching.models import UserProfile


def test_manifest_public_metadata_and_icons():
    client = TestClient(app)
    response = client.get("/chat/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    manifest = response.json()
    assert (manifest["lang"], manifest["dir"], manifest["display"]) == ("he", "rtl", "standalone")
    assert manifest["start_url"] == manifest["scope"] == "/chat"
    assert [icon["sizes"] for icon in manifest["icons"]] == ["192x192", "512x512"]
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/chat", follow_redirects=False).status_code == 302


def test_chat_markup_adapts_language_without_cached_private_html():
    profile = UserProfile(user_id="u1", name="Test", phone_number="+972500000001", language="he")
    with patch("autogpt.coaching.api._get_user_id_from_cookie", return_value="u1"), \
         patch("autogpt.coaching.api.get_user_profile", return_value=profile):
        response = TestClient(app).get("/chat")
    assert response.status_code == 200
    assert '<html lang="he" dir="rtl">' in response.text
    assert '<link rel="manifest" href="/chat/manifest.webmanifest">' in response.text
    assert 'rel="apple-touch-icon"' in response.text
    assert "serviceWorker.register" not in response.text
