"""Model HTML must not leak markup into Telegram or send unsupported list tags."""
from autogpt.coaching.telegram_format import telegram_html


def test_hebrew_summary_html_and_lists_render_as_supported_telegram_html():
    raw = ('תודה רבה, איזי. סיכום המפגש נשמר.\n'
           '<b>יעד מרכזי</b><ul><li>הצלחה קודמת</li><li><b>פעולה לשבוע הבא</b></li></ul>'
           '<p>אנרגיה: <i>גבוהה</i></p>')
    result = telegram_html(raw)
    assert 'תודה רבה, איזי' in result
    assert '<b>יעד מרכזי</b>' in result
    assert '• הצלחה קודמת' in result
    assert '• <b>פעולה לשבוע הבא</b>' in result
    assert '<i>גבוהה</i>' in result
    assert all(x not in result for x in ('&lt;b&gt;', '<ul>', '<li>', '<p>'))


def test_plain_markdown_still_supported_and_unsafe_markup_escaped():
    result = telegram_html('**הצלחה** <script>alert(1)</script> 2 < 3')
    assert '<b>הצלחה</b>' in result
    assert '<script>' not in result and 'alert(1)' not in result
    assert '2 &lt; 3' in result


def test_links_are_restricted_and_entities_not_double_escaped():
    result = telegram_html('<a href="javascript:alert(1)">bad</a> &amp; '
                           '<a href="https://example.com?a=1&amp;b=2">safe</a>')
    assert 'javascript:' not in result
    assert 'bad &amp; ' in result
    assert '<a href="https://example.com?a=1&amp;b=2">safe</a>' in result


def test_unclosed_supported_tag_closed_for_telegram():
    assert telegram_html('<b>מיקוד') == '<b>מיקוד</b>'
