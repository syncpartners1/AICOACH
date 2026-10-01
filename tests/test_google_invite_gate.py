"""Unverified legacy signup paths must fail closed; no auto-activation."""
import base64
from unittest.mock import patch
from fastapi.testclient import TestClient
from autogpt.coaching.api import app


def test_unverified_gid_disabled_before_storage():
    with patch('autogpt.coaching.api.google_auth') as helper:
        r=TestClient(app).post('/public/complete-google-signup',json={
            'gid':base64.urlsafe_b64encode(b'g9|Name|test@example.invalid').decode(),
            'phone_number':'+972500000000','invite_token':'any'})
    assert r.status_code==410
    helper.assert_not_called()


def test_raw_google_id_disabled_even_with_api_key():
    r=TestClient(app).post('/auth/google/token',json={'google_id':'g9','email':'test@example.invalid','phone_number':'+972500000000','name':'Test'})
    assert r.status_code==410
    assert 'set-cookie' not in r.headers


def test_phone_setup_cannot_accept_gid():
    assert TestClient(app).get('/phone-setup?gid=anything').status_code==410


def test_registration_retains_local_google_route():
    r=TestClient(app).get('/register')
    assert '/auth/google/url?redirect_to=' in r.text
    assert 'location.pathname + location.search' in r.text
