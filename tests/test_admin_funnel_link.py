"""The admin page links to the funnel screen."""
from autogpt.coaching.admin_ui import render_admin


def test_admin_page_links_to_the_funnel_screen_in_both_languages():
    for lang in ("he", "en"):
        html = render_admin(users=[], pending_invites=[], public_url="https://app.changenavigator.co.il",
                            pending_users=[], lang=lang)
        assert '<a href="/admin/funnel">משפך לקוחות</a>' in html
        # next to the existing work shortcuts, not instead of them
        for href in ("/admin/booking-notifications", "/admin/messages", "/admin/coaching-leads", "/admin/work-orders"):
            assert 'href="%s"' % href in html
