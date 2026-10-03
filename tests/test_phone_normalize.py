"""One person, one phone format (E.164), across work orders, lead contacts, bookings and signups."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import booking_notifications as b
from autogpt.coaching.phone import normalize_phone, require_phone

# The four formats found in the live data, plus common typing variants.
ISRAELI = ["+972501234567", "+972 50-123-4567", "+972 50 123 4567", "0501234567",
           "050-123-4567", "050 123 4567", "(050) 1234567", "972501234567", "00972501234567",
           "501234567", " 0501234567 "]


@pytest.mark.parametrize("raw", ISRAELI)
def test_israeli_formats_become_one_number(raw):
    assert normalize_phone(raw) == "+972501234567"


def test_landline_and_voip():
    assert normalize_phone("03-1234567") == "+97231234567"
    assert normalize_phone("077-1234567") == "+972771234567"


@pytest.mark.parametrize("raw,expected", [("+1 415 555 0123", "+14155550123"), ("0044 20 7946 0958", "+442079460958"),
                                          ("+44 (0)20 7946 0958".replace("(0)", ""), "+442079460958")])
def test_international_with_plus_or_00(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "abc", "050123", "+972 5012", "+0501234567", "14155550123x",
                                 "+1", "0501234567890123", "+972 0501234567", "٠٥٠١٢٣٤٥٦٧"])
def test_invalid_is_none_not_a_guess(raw):
    assert normalize_phone(raw) is None


def test_require_phone_raises():
    assert require_phone("050-123-4567") == "+972501234567"
    with pytest.raises(ValueError):
        require_phone("12")


def booking(**kw):
    data = dict(event_id="e1", name="A", email="a@example.test", start="2026-10-01T12:00:00Z",
                end="2026-10-01T13:00:00Z", meeting_type="intro_30")
    return b.NewBooking(**{**data, **kw})


def test_booking_phone_optional_normalized_and_validated():
    assert booking().phone is None
    assert booking(phone="").phone is None
    assert booking(phone="050-123-4567").phone == "+972501234567"
    with pytest.raises(ValueError):
        booking(phone="12")


def test_booking_without_phone_keeps_old_payload_shape():
    """A stored pre-phone booking must still compare equal when the same event is delivered again."""
    assert "phone" not in booking().model_dump(mode="json", exclude_none=True)
    assert booking(phone="0501234567").model_dump(mode="json", exclude_none=True)["phone"] == "+972501234567"


def test_booking_mail_shows_phone_when_given():
    with patch("autogpt.coaching.email_service.send_notification_email") as send:
        b.notify_email(booking(phone="0501234567"))
    assert "+972501234567" in str(send.call_args)
    with patch("autogpt.coaching.email_service.send_notification_email") as send:
        b.notify_email(booking())
    assert "טלפון" not in str(send.call_args)


# ---- work orders and lead contact: normalized when saved, invalid blocked ----
from autogpt.coaching.api import app  # noqa: E402
from tests.test_work_orders_drafts import _client as wo_client  # noqa: E402


def _draft(**kw):
    return {"customer_name": "Test", "customer_identity": "123456789", "customer_email": "test@example.org",
            "customer_phone": "050-123-4567", "customer_address": "Test street 1", "track": "personal",
            "plan": "full", "price_key": "personal_clinic_full", "amount_ils": "4500.00", **kw}


def test_work_order_saves_e164_and_blocks_invalid(monkeypatch):
    client = wo_client(monkeypatch)
    hdr = {"Origin": "https://app.changenavigator.co.il"}
    with patch("autogpt.coaching.work_orders.execute_query") as db:
        assert client.post("/admin/work-orders/drafts", json=_draft(), headers=hdr).status_code == 200
        assert "+972501234567" in db.call_args.args[1] and "050-123-4567" not in db.call_args.args[1]
        db.reset_mock()
        bad = client.post("/admin/work-orders/drafts", json=_draft(customer_phone="12"), headers=hdr)
        assert bad.status_code == 422 and db.call_count == 0


def test_lead_contact_saves_e164_and_blocks_invalid(monkeypatch):
    from tests.test_admin_lead_orders import client as lead_client, ID
    c = lead_client(monkeypatch)
    cursor = MagicMock(); cursor.fetchone.return_value = {"submission_id": ID}

    @contextmanager
    def transaction(**kwargs):
        yield cursor
    hdr = {"Origin": "https://changenavigator.web.app"}
    data = {"name": "ישראל ישראלי", "email": "test@example.org", "mobile_phone": "050-123-4567"}
    with patch("autogpt.coaching.admin_lead_orders.get_db_cursor", transaction):
        assert c.put(f"/admin/coaching-leads/{ID}/contact", json={**data, "mobile_phone": "12345678x"},
                     headers=hdr).status_code == 422
        assert cursor.execute.call_count == 0
        assert c.put(f"/admin/coaching-leads/{ID}/contact", json=data, headers=hdr).status_code == 200
        assert cursor.execute.call_args_list[1].args[1][3] == "+972501234567"


# ---- users: new rows normalized; old-format rows are still found; no regression for odd input ----
class _Table:
    def __init__(self, rows):
        self.rows, self.inserted, self._eq = rows, [], None

    def select(self, *a):
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def insert(self, row):
        self.inserted.append(row)
        return self

    def execute(self):
        if self._eq:
            col, val = self._eq
            self._eq = None
            return MagicMock(data=[r for r in self.rows if r.get(col) == val])
        return MagicMock(data=[])


def _db(rows):
    t = _Table(rows)
    return MagicMock(table=lambda name: t), t


def test_signup_stores_e164():
    from autogpt.coaching import storage
    db, table = _db([])
    with patch.object(storage, "_get_client", return_value=db):
        storage.register_user_by_phone("A", "050-123-4567")
    assert table.inserted[0]["phone_number"] == "+972501234567"


def test_signup_rejects_same_number_in_another_format_and_in_old_format():
    from autogpt.coaching import storage
    for stored in ("+972501234567", "050-123-4567"):
        db, _ = _db([{"user_id": "u1", "phone_number": stored}])
        with patch.object(storage, "_get_client", return_value=db):
            with pytest.raises(ValueError):
                storage.register_user_by_phone("A", "0501234567" if stored.startswith("+") else "050-123-4567")


def test_lookup_finds_old_format_row_by_its_own_text():
    from autogpt.coaching import storage
    row = {"user_id": "u1", "name": "A", "phone_number": "+972 50-123-4567", "email": None,
           "account_status": "active", "language": "he"}
    db, _ = _db([row])
    with patch.object(storage, "_get_client", return_value=db):
        assert storage.get_user_by_phone("+972 50-123-4567").user_id == "u1"
        assert storage.get_user_by_phone("+972501234567") is None  # unchanged: old rows need the cleanup step


def test_unrecognised_number_is_kept_as_given_for_signup():
    from autogpt.coaching import storage
    db, table = _db([])
    with patch.object(storage, "_get_client", return_value=db):
        storage.register_user_by_phone("A", "tg-12345")
    assert table.inserted[0]["phone_number"] == "tg-12345"
