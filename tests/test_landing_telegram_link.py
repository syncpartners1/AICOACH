from pathlib import Path

LANDING = Path(__file__).resolve().parents[1] / "public" / "index.html"


def test_landing_telegram_button_points_to_production_bot():
    html = LANDING.read_text(encoding="utf-8")
    assert 'href="https://t.me/Change_navigator_bot"' in html
    assert "Change_coach_bot" not in html
