"""Qualify-form rebrand scope tests: the Hebrew readiness questionnaire carries
the new Change Navigator icon in its injected header and its own favicon link,
while every other themed page keeps the existing default logo asset."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app

NEW_ICON = "/static/cn-icon-192.png"
NEW_WORDMARK = "/static/cn-logo-white.svg"
OLD_ICON = "/static/android-chrome-192x192.png"


def test_qualify_form_uses_new_brand_icon_in_header_and_favicon():
    html = TestClient(app).get("/qualify-form").text
    # White brand wordmark in the injected header and no duplicated
    # "Change Navigator" text span next to it (the wordmark carries the name).
    assert f'<div class="cn-hdr"><img src="{NEW_WORDMARK}" alt=""></div>' in html
    assert "<span>Change Navigator</span>" not in html
    assert f'<link rel="icon" type="image/png" href="{NEW_ICON}">' in html
    # The old asset must not be referenced anywhere on this page.
    assert OLD_ICON not in html


def test_qualify_form_heading_matches_requested_wording():
    html = TestClient(app).get("/qualify-form").text
    assert "<h2>שאלון מקדים לפגישת איבחון ללא עלות וללא התחייבות</h2>" in html
    assert "<title>שאלון מקדים לפגישת איבחון ללא עלות וללא התחייבות</title>" in html
    # The old term was corrected by the owner: the meeting is פגישת איבחון.
    assert "שיחת הגילוי" not in html
    assert "לפני פגישת האיבחון" in html


def test_qualify_form_questions_and_submit_flow_untouched():
    html = TestClient(app).get("/qualify-form").text
    for marker in ("שאלות מוכנות", "שליחת השאלון", "/coaching-qualify"):
        assert marker in html


def test_other_themed_pages_use_default_brand_wordmark():
    client = TestClient(app)
    en = client.get("/qualify-form-en").text
    assert f'<div class="cn-hdr"><img src="{NEW_WORDMARK}" alt=""></div>' in en
    assert OLD_ICON not in en
    assert NEW_ICON not in en
    assert 'src="/static/cn-logo-black.svg"' in en  # print-only document logo


def test_apply_theme_default_signature_unchanged_for_other_callers():
    from autogpt.coaching.theme import apply_theme
    page = apply_theme("<html><head></head><body><p>x</p></body></html>")
    assert f'<div class="cn-hdr"><img src="{NEW_WORDMARK}" alt=""></div>' in page
    assert "<span>Change Navigator</span>" not in page
    assert 'class="cn-print-logo"' in page
    page2 = apply_theme("<html><head></head><body><p>x</p></body></html>",
                        logo_url=NEW_WORDMARK)
    assert f'<img src="{NEW_WORDMARK}" alt=""' in page2
    assert "<span>Change Navigator</span>" not in page2


APPROVED_INTRO = ("אימון הוא תהליך ממוקד בעשייה בהווה ליצירת העתיד הרצוי: "
                  "מגדירים מה רוצים לשנות, מזהים חסמים ומתקדמים בצעדים מעשיים. "
                  "הוא אינו ייעוץ חד־פעמי ואינו טיפול פסיכולוגי.")


def test_qualify_form_approved_coaching_intro_and_revised_questions():
    html = TestClient(app).get("/qualify-form").text
    # Owner-approved intro paragraph (approved verbatim 2026-11-14).
    assert APPROVED_INTRO in html
    # Owner revisions: 3 months (not 3-6) and real-change wording.
    assert "אתה/את מוכן/ה להתחייב לתהליך מובנה של 3 חודשים?" in html
    assert "3-6 חודשים" not in html
    assert "אתה/את מחפש/ת לבצע שינוי אמיתי, ולא ייעוץ חד-פעמי או טיפול פסיכולוגי?" in html
    # Unchanged questions stay.
    assert "האתגר הזה הוא עדיפות אמיתית עבורך עכשיו?" in html
    assert "תוכל/י להשלים משימות שבועיות באופן עקבי ובזמן?" in html
    assert "המטרה שלך היא לבנות יכולת חדשה, לא רק פתרון מהיר?" in html


def test_qualify_form_brand_colors_scoped_to_form_only():
    client = TestClient(app)
    he = client.get("/qualify-form").text
    # Brand palette on the form: navy header/submit family, tinted background,
    # navy selected-yes instead of green/red defaults.
    assert "background:#ffffff;color:#1e293b" in he
    assert "Assistant" in he
    assert ".yn-btn.active-yes{background:#032b7d;border-color:#032b7d;color:#fff}" in he
    assert ".yn-btn.active-no{background:#e2e8f0;border-color:#94a3b8;color:#334155}" in he
    # Unrelated forms are not recolored.
    consult = client.get("/consult-form").text
    assert "background:#f8fafc;color:#1e293b" in consult
    assert "active-yes{background:#032b7d" not in consult


def test_coach_summary_label_uses_three_months():
    import inspect
    from autogpt.coaching import wix_qualify
    src = inspect.getsource(wix_qualify)
    assert "Ready to commit 3 months?" in src
    assert "3-6 months" not in src
