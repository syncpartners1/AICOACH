"""Brand logo set (navy 10 / white 11 / black 12) wiring across screens and documents.

The white wordmark is the in-screen logo on navy headers (admin screens,
trainee area), the navy wordmark on light cards (sign-in, registration),
and the black wordmark in print output and generated documents.
"""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app

WHITE = "/static/cn-logo-white.svg"
NAVY = "/static/cn-logo-navy.svg"
BLACK = "/static/cn-logo-black.svg"
SITE_ICON = "/static/cn-icon-site-192.png"
TR_ICON = "/static/cn-icon-trainee-192.png"
WHEEL = "/static/android-chrome-192x192.png"


def test_trainee_signin_uses_navy_logo_on_light_card():
    html = TestClient(app).get("/login").text
    assert f'src="{NAVY}"' in html
    assert f'<img src="{WHEEL}"' not in html


def test_admin_login_and_registration_pages_use_navy_logo():
    # These pages need a token/DB to render; assert the served markup in source.
    import inspect
    from autogpt.coaching import api
    src = inspect.getsource(api)
    assert src.count(f'<img src="{NAVY}" alt="Change Navigator logo">') == 2  # admin login + registration
    assert src.count(f'<img src="{NAVY}" style="height:32px;width:auto" alt="Change Navigator logo">') == 1  # sign-in
    assert f'<img src="{WHITE}" style="height:24px;width:auto" alt="Change Navigator logo">' in src  # chat hdr


def test_brand_logo_assets_served():
    client = TestClient(app)
    for path in (WHITE, NAVY, BLACK, "/static/cn-logo-white-858.png", "/static/cn-logo-navy-858.png"):
        assert client.get(path).status_code == 200, path


def test_qualify_form_print_output_carries_black_logo():
    html = TestClient(app).get("/qualify-form").text
    assert f'class="cn-print-logo" src="{BLACK}"' in html


def test_work_order_contract_document_carries_navy_logo_data_uri():
    from autogpt.coaching.work_order_contract import contract_html
    row = {"order_id": "x", "customer_name": "x", "customer_identity": "1",
           "organization_contact": "", "customer_email": "a@b.co", "customer_phone": "1",
           "customer_address": "a", "track": "personal", "plan": "full",
           "price_key": "personal_clinic_full", "amount_agorot": 100, "vat_mode": "plus_vat",
           "notes": "", "payment_schedule": "s"}
    html = contract_html(row)
    assert 'data:image/png;base64,' in html and 'alt="Change Navigator"' in html


def test_role_specific_tab_icons():
    import inspect
    from autogpt.coaching import api, admin_ui, dashboard_ui
    src = inspect.getsource(api)
    # Admin login + generic favicon redirect -> website icon 18.
    assert src.count(f'<link rel="icon" type="image/png" href="{SITE_ICON}">') == 1
    assert f'RedirectResponse(url="{SITE_ICON}", status_code=301)' in src
    # Trainee sign-in, registration, pending -> trainee icon 27.
    assert src.count(f'<link rel="icon" type="image/png" href="{TR_ICON}">') == 3
    # Admin screens -> site icon; trainee dashboard -> trainee icon.
    assert SITE_ICON in inspect.getsource(admin_ui)
    assert TR_ICON in inspect.getsource(dashboard_ui)


def test_site_icon_assets_served():
    client = TestClient(app)
    for path in (SITE_ICON, "/static/cn-icon-site-512.png"):
        assert client.get(path).status_code == 200, path
