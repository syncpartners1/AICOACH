from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def test_static_maps_entry_is_exact_host_and_local_destination():
    html = (ROOT / 'public/index.html').read_text()
    assert "window.location.hostname === 'maps.changenavigator.co.il'" in html
    assert "window.location.pathname === '/' || window.location.pathname === '/index.html'" in html
    assert "window.location.replace('/maps-local/' + window.location.search + window.location.hash)" in html
    assert html.index('id="maps-root-entry"') < html.index('<title>')
    assert '<noscript>' in html
    assert 'href="https://maps.changenavigator.co.il/maps-local/"' in html
    assert 'serviceWorker.register' not in html
    assert 'document.cookie' not in html

def test_root_navigation_not_cached_and_existing_rewrite_preserved():
    config = json.loads((ROOT / 'firebase.json').read_text())['hosting']
    assert config['site'] == 'changenavigator'
    assert config['public'] == 'public'
    assert config['rewrites'] == [{'source': '**', 'run': {'serviceId': 'change-navigator', 'region': 'me-west1'}}]
    headers = {h['source']: h['headers'] for h in config['headers']}
    for path in ['/', '/index.html']:
        assert {'key': 'Cache-Control', 'value': 'no-store'} in headers[path]
