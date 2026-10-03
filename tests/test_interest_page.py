"""Interest pages: /interest and /interest-en."""
import json
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching.api import app
from autogpt.coaching.phone import normalize_phone

PAGES = [("/interest", "he", "rtl"), ("/interest-en", "en", "ltr")]


@pytest.mark.parametrize("path,lang,direction", PAGES)
def test_page_has_the_three_fields_honeypot_and_posts_to_the_save_endpoint(path, lang, direction):
    r = TestClient(app).get(path)
    assert r.status_code == 200
    html = r.text
    assert 'lang="%s" dir="%s"' % (lang, direction) in html
    for el in ('id="name"', 'id="email"', 'id="phone"', 'id="website"', 'id="btn"'):
        assert el in html
    assert 'type="tel"' in html and 'type="email"' in html
    assert "/interest/submit" in html and "source:'interest-page'" in html
    assert 'id="cn-theme"' in html  # shared theme and header
    assert not re.search(r"__[A-Z]+__", html)  # every placeholder was filled
    assert "QMark" not in html and "QMARK" not in html


def test_hebrew_page_uses_the_brand_wording_and_english_page_is_english():
    he = TestClient(app).get("/interest").text
    en = TestClient(app).get("/interest-en").text
    assert "מספר טלפון" in he and "שיחת היכרות" in he and "מספר מחו״ל מתחיל בסימן פלוס" in he
    assert "Phone number" in en and "intro call" in en and "starts with a plus" in en


@pytest.mark.parametrize("path", ["/interest", "/interest-en"])
def test_redirect_only_to_https_and_after_the_thank_you_message(path):
    html = TestClient(app).get(path).text
    assert "/^https:\\/\\//.test(url)" in html
    assert html.index("thanks').style.display='block'") < html.index("window.location.href=url")
    assert "setTimeout" in html


@pytest.mark.parametrize("path", ["/interest", "/interest-en"])
def test_honeypot_is_hidden_without_moving_it_off_screen(path):
    html = TestClient(app).get(path).text
    css = re.search(r"\.hp\{[^}]*\}", html).group(0)
    assert "opacity:0" in css and "-9999" not in css  # an off-screen box makes RTL pages scroll sideways
    assert 'tabindex="-1"' in html and 'autocomplete="off"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_phone_check_matches_the_server_on_many_inputs():
    html = TestClient(app).get("/interest").text
    func = re.search(r"function normPhone\(raw\)\{.*?\n\}\n", html, re.S).group(0)
    cases = ["050-123-4567", "0501234567", "972501234567", "501234567", "+972 50 123 4567", "00972501234567",
             " (050) 123.4567 ", "+1 212 555 0100", "0044 20 7946 0958", "03-123-4567", "", "abc", "12",
             "050-123", "+0501234567", "+123", "+1234567890123456", "+972 0 501234567", "0721234567", "1234567"]
    out = json.loads(subprocess.check_output(
        ["node", "-e", func + "console.log(JSON.stringify(%s.map(normPhone)))" % json.dumps(cases)], text=True))
    assert out == [normalize_phone(c) for c in cases]


def test_pages_only_read_and_the_only_request_is_the_save_post():
    for path in ("/interest", "/interest-en"):
        html = TestClient(app).get(path).text
        assert html.count("fetch(") == 1 and "method:'POST'" in html
