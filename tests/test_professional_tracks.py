"""Professional-track foundation must not mutate engine/contract/session state."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
import pytest

from autogpt.coaching.program_tracks import TRACK_IDS, TRACKS, TrackConflict, set_professional_track

UID = '11111111-1111-4111-8111-111111111111'


def test_catalog_matches_actual_map_tracks_not_coach_aids():
    source = (Path(__file__).parents[1] / 'autogpt/coaching/session_maps.html').read_text()
    start = source.index('[', source.index('const COACHING_TRACKS ='))
    tracks, _ = json.JSONDecoder().raw_decode(source[start:])
    assert TRACK_IDS == {t['id'] for t in tracks if t['id'] != 'coach_aids'}
    assert len(TRACKS) == 6


@pytest.mark.parametrize('track', sorted(TRACK_IDS))
def test_all_six_tracks_append_event_and_preserve_unrelated_fields(track):
    cur = MagicMock()
    cur.fetchone.side_effect = [{'user_id': UID}, {'coaching_track': None},
                               {'user_id': UID, 'coaching_track': track, 'phase': 'meeting_3',
                                'program_type': 'base', 'plan_json': {'goal': 'unchanged'}}]
    @contextmanager
    def cursor(**kwargs):
        assert kwargs == {'commit': True}
        yield cur
    with patch('autogpt.coaching.db.get_db_cursor', cursor):
        result = set_professional_track(UID, track, None)
    assert result['coaching_track'] == track
    statements = [c.args[0] for c in cur.execute.call_args_list]
    writes = [q for q in statements if q.lstrip().startswith('INSERT')]
    assert len(writes) == 2
    assert 'coaching_track_events' in writes[1]
    update = writes[0].split('DO UPDATE SET')[1]
    assert 'phase' not in update and 'program_type' not in update and 'plan_json' not in update
    assert all(x not in '\n'.join(statements) for x in ('invites', 'work_order', 'coaching_sessions'))


def test_stale_change_is_rejected_before_writes():
    cur = MagicMock()
    cur.fetchone.side_effect = [{'user_id': UID}, {'coaching_track': 'career'}]
    @contextmanager
    def cursor(**kwargs): yield cur
    with patch('autogpt.coaching.db.get_db_cursor', cursor), pytest.raises(TrackConflict):
        set_professional_track(UID, 'startup', 'personal')
    assert not any('INSERT' in c.args[0] for c in cur.execute.call_args_list)


def test_retry_same_track_is_noop_without_duplicate_event():
    cur = MagicMock()
    cur.fetchone.side_effect = [{'user_id': UID}, {'coaching_track': 'startup'}, {'coaching_track': 'startup'}]
    @contextmanager
    def cursor(**kwargs): yield cur
    with patch('autogpt.coaching.db.get_db_cursor', cursor):
        assert set_professional_track(UID, 'startup', None)['coaching_track'] == 'startup'
    assert not any('INSERT' in c.args[0] for c in cur.execute.call_args_list)


@pytest.mark.parametrize('value', ['base', 'coach_aids', '', 'unknown'])
def test_invalid_track_never_opens_database(value):
    with patch('autogpt.coaching.db.get_db_cursor') as cur, pytest.raises(ValueError):
        set_professional_track(UID, value, None)
    cur.assert_not_called()


def test_screen_disambiguates_curriculum_and_track_escapes_identity():
    from autogpt.coaching.admin_program_ui import render_program_editor
    from autogpt.coaching.models import UserProfile
    page = render_program_editor(UserProfile(user_id=UID, name='<unsafe>', phone_number='+972501234567'),
                                 {'coaching_track': 'startup', 'program_type': 'base_financial', 'phase': 'meeting_3'})
    assert '<unsafe>' not in page and '&lt;unsafe&gt;' in page
    assert 'value="startup" selected' in page
    assert 'value="base_financial" selected' in page
    assert 'הגדרות תוכנית הבוט הקיימות' in page
    assert 'לא משנה מפגשים קודמים' in page
    assert 'expected_track' in page and 'button.disabled = true' in page
    assert 'פתח מחדש ובדוק לפני ניסיון נוסף' in page


def test_professional_endpoint_auth_validation_and_conflict():
    from autogpt.coaching.api import app, verify_admin_or_api_key
    from fastapi.testclient import TestClient
    client = TestClient(app, headers={"Origin": "http://testserver"})
    path = f'/admin/users/{UID}/professional-track'
    assert client.put(path, json={'coaching_track': 'startup'}).status_code == 403
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    try:
        with patch('autogpt.coaching.program_tracks.set_professional_track', return_value={'coaching_track': 'startup'}) as save:
            r = client.put(path, json={'coaching_track': 'startup', 'expected_track': None})
            assert r.status_code == 200
            save.assert_called_once_with(UID, 'startup', None)
        with patch('autogpt.coaching.program_tracks.set_professional_track', side_effect=TrackConflict('reload')):
            assert client.put(path, json={'coaching_track': 'startup'}).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_admin_table_uses_saved_professional_label():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import UserProgressSummary
    page = render_admin([UserProgressSummary(user_id=UID, name='Test', phone_number='+1', coaching_track='startup', program_type='base_financial')], [], lang='he')
    assert 'הקמת עסק ויזמות' in page
    assert '<strong>מסלול מקצועי:</strong>' in page
    assert '<strong>תוכנית הבוט:</strong> בסיס + מעטפת כלכלית' in page
    assert 'מסלול מקצועי ותוכנית בוט' in page
    assert '.members-table .col-name,.members-table .col-actions{position:static}' in page


def test_cross_origin_rejected_without_write():
    from autogpt.coaching.api import app, verify_admin_or_api_key
    from fastapi.testclient import TestClient
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    try:
        with patch('autogpt.coaching.program_tracks.set_professional_track') as save:
            client = TestClient(app)
            assert client.put(f'/admin/users/{UID}/professional-track', json={'coaching_track':'startup'}).status_code == 403
            assert client.put(f'/admin/users/{UID}/professional-track', headers={'Origin':'https://outside.invalid'}, json={'coaching_track':'startup'}).status_code == 403
            save.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_admin_table_unassigned_track_keeps_both_labels_in_english():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import UserProgressSummary
    page = render_admin([UserProgressSummary(user_id=UID, name='Test', phone_number='+1', program_type='base')], [], lang='en')
    assert '<strong>Professional track:</strong> Professional track not assigned' in page
    assert '<strong>Bot curriculum:</strong> Base program' in page
    assert 'Professional track and bot curriculum' in page


def test_track_history_fk_follows_profile_deletion_without_new_retention_job():
    root = Path(__file__).parents[1] / 'autogpt/coaching'
    sql = (root / 'program_tracks.sql').read_text()
    assert 'user_id UUID NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE' in sql
    assert 'DELETE FROM' not in sql
    assert 'coaching_track_events_user_id_fkey' in (root / 'program_tracks_verify.sql').read_text()
