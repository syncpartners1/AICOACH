"""Members table layout: horizontal scroll wrapper, sticky actions column, email column."""
from types import SimpleNamespace

from autogpt.coaching.admin_ui import render_admin


def _user(email="trainee@example.com", user_id="u1", status_val="active"):
    return SimpleNamespace(
        user_id=user_id, name="Trainee", phone_number="+972000000", email=email,
        telegram_user_id=None, last_session=None, last_weekly_plan=None,
        program_type="base", phase="meeting_3",
        objectives_count=0, avg_kr_pct=0,
        account_status=SimpleNamespace(value=status_val),
    )


def _page(lang="en", users=None):
    return render_admin(users=[_user()] if users is None else users,
                        pending_invites=[], lang=lang)


def test_tables_wrapped_in_horizontal_scroll_container():
    page = _page()
    # all three card tables (pending, members, invites) sit inside a scroll wrapper
    assert page.count('<div class="tbl-wrap">') == 3
    assert "overflow-x:auto" in page


def test_actions_column_is_sticky():
    page = _page()
    assert 'class="col-actions"' in page            # th and td both carry the class
    assert "position:sticky" in page
    assert "inset-inline-end:0" in page             # logical property: correct in RTL and LTR


def test_sticky_cells_keep_header_and_hover_background():
    page = _page()
    assert "thead th.col-actions{{background:#f9fafb}}".replace("{{", "{").replace("}}", "}") in page
    assert "tbody tr:hover td.col-actions{{background:#f9fafb}}".replace("{{", "{").replace("}}", "}") in page


def test_email_column_header_both_languages():
    assert "Email" in _page("en")
    page_he = _page("he")
    assert "אימייל" in page_he
    assert ">Email<" not in page_he


def test_email_value_rendered_and_escaped():
    page = _page(users=[_user(email="a<b>@example.com")])
    assert "a&lt;b&gt;@example.com" in page
    assert "a<b>@example.com" not in page


def test_email_placeholder_when_missing():
    page = _page(users=[_user(email=None)])
    assert "trainee@example.com" not in page
    page_empty = _page(users=[_user(email="")])
    assert page_empty.count("—") >= 1


def test_empty_members_colspan_covers_email_column():
    page = _page(users=[])
    assert 'colspan="11"' in page
    assert 'colspan="10"' not in page
