from fastapi.testclient import TestClient
from autogpt.coaching.api import app
from autogpt.coaching.pwa_install_ui import INSTALL_HTML
from autogpt.coaching.production_ui import PRODUCTION_HTML

def test_install_page_public_and_hebrew():
    response = TestClient(app).get('/chat/install')
    assert response.status_code == 200
    assert '<html lang="he" dir="rtl">' in response.text
    assert '<svg role="img"' in response.text
    assert 'https://app.changenavigator.co.il/chat/install' in response.text
    assert all(name in response.text for name in ['Safari','Chrome','Microsoft Edge','Samsung Internet'])
    assert 'Add to phone' in response.text and 'Homescreen' in response.text
    assert 'לעיתים נוצר קיצור דרך' in response.text
    assert 'href="/chat"' in response.text
    assert 'href="/chat/manifest.webmanifest"' in response.text
    assert "register('/chat/sw.js',{scope:'/chat'})" in response.text

def test_entry_points_and_privacy():
    assert 'href="/chat/install"' in PRODUCTION_HTML
    assert 'href="/chat/install"' in TestClient(app).get('/').text
    assert 'href="/chat/install"' in TestClient(app).get('/login').text
    assert TestClient(app).get('/chat', follow_redirects=False).status_code == 302
    assert 'beforeinstallprompt' in INSTALL_HTML
    assert 'userChoice' in INSTALL_HTML and 'appinstalled' in INSTALL_HTML
    assert 'id="install" hidden' in INSTALL_HTML
    assert 'https://api.qr' not in INSTALL_HTML
    assert 'Notification.requestPermission' not in INSTALL_HTML
    from autogpt.coaching.chat_pwa import CHAT_SW
    assert "url.pathname !== '/chat'" in CHAT_SW


def test_firebase_main_install_entry_matches_backend_and_keeps_login():
    from pathlib import Path
    import json
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "firebase.json").read_text())
    assert config["hosting"]["public"] == "public"
    html = (root / "public" / "index.html").read_text()
    assert html.count('href="/chat/install"') == 1
    assert 'lang="he">הוספה למסך הבית</a>' in html
    assert 'הכניסה לחשבון נשארת נפרדת' in html
    assert html.index('href="/chat/install"') < html.index('href="/auth/google/url')
    assert 'href="/chat"' in html and 'href="/login"' in html
    assert 'beforeinstallprompt' not in html
    assert 'Notification.requestPermission' not in html
