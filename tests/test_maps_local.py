import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from autogpt.coaching import maps_local as m, api


def test_library_strips_private_actions_and_keeps_all_content():
    html,version=m.library_html()
    assert m.MARKER in html and version in html
    assert 'localStorage' not in html and 'indexedDB' not in html
    for forbidden in ('logTraineeSelect','saveLogToFile','copyCaptainsLog','/admin/active-trainees','/sessions','logClientName','fetch('):
        assert forbidden not in html
    assert 'מחוויית שיא לצעד הבא' in html and 'REACTION_MAPS' in html and 'setDuration' in html
    assert 'navigator.serviceWorker.register' in html and 'ללא שמירת סיכומים' in html
    assert '<a href="/maps-local/"' not in html  # online setup link is not duplicated locally


def test_manifest_scope_and_real_icons():
    manifest=json.loads(m.manifest())
    assert manifest['start_url']==manifest['scope']==manifest['id']=='/maps-local/'
    assert manifest['display']=='standalone'
    root=Path(__file__).parents[1]/'autogpt'
    for icon in manifest['icons']:assert (root/icon['src'].lstrip('/')).exists()


def test_worker_only_caches_maps_content_and_static_assets():
    sw=m.service_worker()
    assert m.MARKER in sw and 'response.redirected' in sw and 'response.ok' in sw
    assert "event.request.method!=='GET'" in sw
    assert "u.pathname===INDEX" in sw and 'ASSETS.includes(u.pathname)' in sw
    assert "k.startsWith('maps-local-')" in sw
    assert "'/admin'" not in sw and 'localStorage' not in sw
    assert 'ACTIVATE_MAPS_UPDATE' in sw


def test_initial_library_auth_and_manifest_worker_public():
    client=TestClient(api.app)
    with patch.object(api,'_is_admin_authenticated',return_value=False):
        r=client.get('/maps-local/');assert r.status_code==401 and m.MARKER not in r.text
        assert r.headers['cache-control']=='no-store'
    with patch.object(api,'_is_admin_authenticated',return_value=True):
        r=client.get('/maps-local/');assert r.status_code==200 and m.MARKER in r.text
        assert r.headers['cache-control']=='no-store, private'
    assert client.get('/maps-local',follow_redirects=False).status_code==307
    assert client.get('/maps-local/manifest.json').json()['scope']=='/maps-local/'
    r=client.get('/maps-local/sw.js');assert r.status_code==200
    assert r.headers['service-worker-allowed']=='/maps-local/'
