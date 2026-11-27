"""The coach-only session-maps page: admin auth required, self-contained, not public."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token

ORIGIN = "https://app.changenavigator.co.il"


def _client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    c.cookies.set("__session", _admin_token())
    return c


def test_session_maps_requires_admin_auth(monkeypatch):
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    # Login page, not the tool: the session-maps data constants must not leak.
    assert 'action="/admin/login"' in r.text
    assert "COACHING_TRACKS" not in r.text


def test_session_maps_served_for_admin(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    assert "Navigator Session Maps" in r.text
    assert 'dir="rtl"' in r.text
    assert 'href="/admin"' in r.text


def test_admin_dashboard_menu_links_session_maps(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin")
    assert r.status_code == 200
    assert 'href="/admin/session-maps"' in r.text


def test_session_maps_has_no_external_references(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    for marker in ("fonts.googleapis.com", "fonts.gstatic.com", "<iframe", "<img",
                   "localStorage", "sessionStorage", "XMLHttpRequest"):
        assert marker not in r.text, marker
    # The Captain's Log save calls the admin API; every call must stay same-origin.
    import re
    calls = re.findall(r"""fetch\(['\"]([^'\"]+)""", r.text)
    assert calls, "expected same-origin admin API calls"
    for url in calls:
        assert url.startswith("/admin/"), url


def test_session_maps_file_outside_public_static():
    import os
    from autogpt.coaching import api as _api

    mod_dir = os.path.dirname(_api.__file__)
    assert os.path.isfile(os.path.join(mod_dir, "session_maps.html"))
    public_static = os.path.join(os.path.dirname(mod_dir), "static")
    assert not os.path.exists(os.path.join(public_static, "session_maps.html"))


def test_default_track_id_exists_in_tracks():
    from pathlib import Path
    import re
    html = (Path(__file__).resolve().parent.parent / "autogpt" / "coaching" / "session_maps.html").read_text(encoding="utf-8")
    m = re.search(r'let currentTrackId = "([^"]+)"', html)
    assert m, "default track id not found"
    assert f'"id": "{m.group(1)}"' in html, f"default track {m.group(1)} not a real track"


def test_captains_log_save_ui_and_wide_layout(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    page = r.text
    # Active-trainee select fed from the live admin users list, no hardcoded names.
    assert 'id="logTraineeSelect"' in page
    assert "fetch('/admin/active-trainees')" in page
    assert "u-demo" not in page
    # Numbered meeting input and the inline phase notice.
    assert 'id="logMeetingNumber"' in page
    assert "מקדם את שלב המתאמן" in page
    # Save posts a manual session with the paid extraction explicitly skipped.
    assert "function saveLogToFile()" in page
    assert "'/admin/users/' + encodeURIComponent(logLinkedUserId) + '/sessions'" in page
    assert "skip_okr_extraction: true" in page
    # Stale-target protection: manual name edit breaks the link and disables save.
    assert "function onLogNameEdited()" in page
    assert "logLinkedUserId = null" in page
    # Unknown-result state warns to check the tracking file before retrying.
    assert "תוצאת השמירה לא ידועה" in page
    # Wide desktop layout: single-lane tools render centered, not in 1/5 column.
    assert ".lanes-grid.single-lane" in page
    assert "single-lane" in page


def test_peak_map_five_source_stages_and_no_invented_timing():
    import json,re
    from pathlib import Path
    text=Path(__file__).parents[1].joinpath('autogpt/coaching/session_maps.html').read_text()
    tracks=json.loads(re.search(r'const COACHING_TRACKS = (\[.*?\]);\s*const ROUTING_ENTRIES',text,re.S).group(1))
    aids=next(t for t in tracks if t['id']=='coach_aids')['sessions']
    peak=next(aid for aid in aids if aid['num']=='כלי 11')
    assert len(aids)==12 and peak['num']=='כלי 11'
    assert peak['name']=='מחוויית שיא לצעד הבא'
    assert len(peak['lanes'])==5
    assert [x['title'] for x in peak['lanes']]==['פתיחה והסכמה','סיפור של שגשוג','רגע השיא','התנאים המאפשרים','מבט קדימה: שאלת Feedforward']
    for lane in peak['lanes']:
        assert set(lane['mins'].values())=={'—'} and lane['branch'] is None
    assert 'תוספת יישום מוצעת, לא מהצילום' in peak['lanes'][4]['prompts'][2]
    assert 'לפני שנודעו לך התוצאות' in peak['lanes'][1]['prompts'][0]
    assert 'מה החמצתי' in peak['lanes'][1]['prompts'][3]
    assert 'שם מחבר' not in peak['name']


def test_peak_map_optional_branch_renderer_keeps_existing_branch_buttons():
    from pathlib import Path
    text=Path(__file__).parents[1].joinpath('autogpt/coaching/session_maps.html').read_text()
    assert '${rxObj ? `<button class="branch-btn"' in text
    assert "openReactionModal('${lane.branch}')" in text
