import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from autogpt.coaching import api, maps_invitations as m


def test_maps_host_disabled_and_unrelated_paths_denied():
    c=TestClient(api.app,base_url='https://maps.changenavigator.co.il')
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'false'}):
        assert c.get('/maps-local/').status_code==404
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'true'}):
        for path in ['/admin','/dashboard/123','/health','/openapi.json','/admin/active-trainees','/static/unknown.png']:
            assert c.get(path).status_code==404
        assert c.get('/maps-local/').status_code==200
        assert 'קוד הזמנה' in c.get('/maps-local/').text
        assert 'maps-local-library' not in c.get('/maps-local/').text
        assert c.get('/maps-local/manifest.json').status_code==200


def test_guest_cookie_never_becomes_admin_or_participant():
    c=TestClient(api.app,base_url='https://app.changenavigator.co.il')
    c.cookies.set('__session','maps1.fake.fake.fake')
    for path in ['/admin','/admin/active-trainees','/dashboard/123','/maps-local/']:
        assert c.get(path).status_code==404


def test_redeem_requires_origin_and_enabled_maps_host():
    c=TestClient(api.app,base_url='https://maps.changenavigator.co.il')
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'true'}):
        assert c.post('/maps-access/redeem',json={'code':'x'}).status_code==403
        with patch.object(m,'redeem',return_value='maps1.scoped.cookie.signature') as redeem:
            r=c.post('/maps-access/redeem',json={'code':'x'},headers={'Origin':'https://maps.changenavigator.co.il'})
            assert r.status_code==200 and redeem.call_count==1
            cookie=r.headers['set-cookie']
            assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Domain=' not in cookie


def test_issue_requires_admin_origin_eligibility_and_explicit_expiry():
    c=TestClient(api.app,base_url='https://app.changenavigator.co.il')
    assert c.post('/admin/maps-invitations',json={}).status_code==403
    with patch.object(api,'_is_admin_authenticated',return_value=True):
        # Router captures the original callable, so use a signed real admin cookie instead.
        pass
    c.cookies.set('__session',api._admin_token())
    assert c.post('/admin/maps-invitations',json={}).status_code==403
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'true'}):
        assert c.post('/admin/maps-invitations',json={},headers={'Origin':'https://app.changenavigator.co.il'}).status_code==400
        assert c.post('/admin/maps-invitations',json={'eligible_tut_franchisee':True},headers={'Origin':'https://app.changenavigator.co.il'}).status_code==400


def test_opening_contact_credits_and_private_actions_unchanged():
    from autogpt.coaching.maps_local import library_html,service_worker
    html,v=library_html()
    for text in ['maps-opening','maps-workspace','Change Navigator | עדי בן נשר','office@changenavigator.co.il','tel:+972547586022','ד"ר דינה ניר','beforeinstallprompt']:
        assert text in html
    assert 'maps-adi-6865.jpg' in service_worker()
    assert 'cn-logo-white-858.png' in service_worker()
    assert 'saveLogToFile' not in html


def test_untrusted_forwarded_host_does_not_escape_maps_boundary():
    c=TestClient(api.app,base_url='https://maps.changenavigator.co.il')
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'true'}):
        assert c.get('/admin',headers={'X-Forwarded-Host':'app.changenavigator.co.il'}).status_code==404
        assert c.get('/health',headers={'X-Forwarded-Host':'app.changenavigator.co.il'}).status_code==404
    proxy=TestClient(api.app,base_url='https://example.run.app')
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'true'}):
        assert proxy.get('/admin',headers={'X-Forwarded-Host':'maps.changenavigator.co.il'}).status_code==404
        assert 'קוד הזמנה' in proxy.get('/maps-local/',headers={'X-Forwarded-Host':'maps.changenavigator.co.il'}).text


def test_issuance_disabled_until_explicit_activation():
    c=TestClient(api.app,base_url='https://app.changenavigator.co.il')
    c.cookies.set('__session',api._admin_token())
    with patch.dict(os.environ,{'MAPS_INVITES_ENABLED':'false'}):
        r=c.post('/admin/maps-invitations',json={},headers={'Origin':'https://app.changenavigator.co.il'})
        assert r.status_code==503
        assert c.get('/admin/maps-invitations').status_code==200


def test_approved_year_window_and_minimal_contact():
    from pathlib import Path
    source=Path(m.__file__).read_text()
    assert "interval '365 days'" in source
    assert 'max_age=365*24*3600' in source
    from autogpt.coaching.maps_opening import opening_html
    assert 'שנה מההפעלה' in opening_html()
    assert 'ד"ר דינה ניר' in opening_html()
    assert '038649679' not in opening_html()
