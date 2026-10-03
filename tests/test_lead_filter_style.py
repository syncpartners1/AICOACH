"""The leads page must keep list rows readable (the shared theme makes buttons white-on-navy)."""
from tests.test_admin_lead_orders import client


def test_rows_dark_text_and_filter_highlight(monkeypatch):
    html = client(monkeypatch).get("/admin/coaching-leads").text
    assert ".item{color:#1a2b4a" in html
    assert "#stageFilter.on{background:#1a2b4a;color:#fff}" in html
    assert "classList.toggle('on',!!filter.value)" in html
