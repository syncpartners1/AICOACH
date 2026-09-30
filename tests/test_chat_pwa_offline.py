"""7.2 public offline shell never caches session or API responses."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from autogpt.coaching.api import app
from autogpt.coaching.models import UserProfile


def test_public_offline_and_worker_without_private_data():
    c = TestClient(app)
    offline = c.get('/chat/offline')
    sw = c.get('/chat/sw.js')
    assert offline.status_code == sw.status_code == 200
    assert 'אין חיבור' in offline.text
    assert 'cache.addAll(PUBLIC)' in sw.text
    assert "url.pathname !== '/chat'" in sw.text
    assert 'fetch(event.request).catch' in sw.text
    assert 'service-worker-allowed' in sw.headers
    assert all(term not in sw.text for term in ['user_id', 'session_id', '/user/session', '/admin'])


def test_authenticated_markup_registers_scoped_worker_and_logout_purges():
    user = UserProfile(user_id='u1', name='Test', phone_number='+972500000001', language='he')
    with patch('autogpt.coaching.api._get_user_id_from_cookie', return_value='u1'), \
         patch('autogpt.coaching.api.get_user_profile', return_value=user):
        page = TestClient(app).get('/chat').text
    assert "register('/chat/sw.js', { scope: '/chat' })" in page
    assert 'onclick="logoutChat(event)"' in page
    assert "caches.delete('chat-shell-v1')" in page
    assert 'navigator.serviceWorker?.getRegistrations()' in page
