"""Qualify-form verdict branch: the on-submit UI must show the PASS diagnostic
booking link, a preliminary-conversation recommendation for BORDERLINE and FAIL, in Hebrew and English."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app

DIAG = "https://meet.changenavigator.co.il/?type=diagnostic_60"


def he():
    return TestClient(app).get("/qualify-form").text


def en():
    return TestClient(app).get("/qualify-form-en").text


def test_hebrew_verdict_blocks_and_deep_link_injected():
    html = he()
    assert "__DIAG_URL__" not in html and "diagnostic_60" in html
    assert 'id="thanksPass"' in html and 'id="thanksOther"' in html
    assert "התשובות שלך עומדות בתנאי השאלון" in html
    assert "מומלץ ללחוץ על הקישור לקביעת פגישת אבחון ללא עלות וללא התחייבות" in html
    assert "שיחה מקדימה" in html
    assert 'id="thanksReview"' not in html
    assert "d.verdict" in html and "'PASS'" in html and "'BORDERLINE'" in html
    assert "link.searchParams.set('name',q8)" in html


def test_english_verdict_blocks_and_deep_link_injected():
    html = en()
    assert "__DIAG_URL__" not in html and "diagnostic_60" in html
    assert 'id="thanksPass"' in html and 'id="thanksOther"' in html
    assert "free, no-obligation diagnostic meeting" in html
    assert "short preliminary conversation" in html
    assert "personally review" not in html
    assert "d.verdict" in html and "'PASS'" in html


def test_old_generic_thanks_removed_from_qualify_pages():
    assert 'id="thanksMsg"' not in he()
    assert 'id="thanksMsg"' not in en()


def test_consult_form_thanks_untouched():
    html = TestClient(app).get("/consult-form").text
    assert 'id="thanksMsg"' in html and "עדי יחזור אליך" in html
