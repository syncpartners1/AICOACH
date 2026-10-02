from autogpt.coaching.theme import apply_theme, LOGO_URL


def test_theme_added_after_page_style_with_header():
    page = '<!doctype html><html><head><style>body{margin:0}</style></head><body><h1>x</h1></body></html>'
    out = apply_theme(page)
    assert out.index('body{margin:0}') < out.index('id="cn-theme"')
    assert 'class="cn-hdr"' in out and LOGO_URL in out
    assert out.index('class="cn-hdr"') < out.index('<h1>')


def test_page_without_body_tag_gets_header_in_flow():
    page = '<html><meta charset="utf-8"><style>a{}</style><h1>x</h1></html>'
    out = apply_theme(page)
    assert out.index('class="cn-hdr"') < out.index('<h1>')


def test_page_without_style_still_themed():
    page = '<html lang="he"><meta charset="utf-8"><h1>x</h1></html>'
    out = apply_theme(page)
    assert 'id="cn-theme"' in out and out.index('class="cn-hdr"') < out.index('<h1>')


def test_idempotent():
    once = apply_theme('<html><style>a{}</style><body></body></html>')
    assert apply_theme(once) == once


def test_screen_only_keeps_print_clean():
    out = apply_theme('<html><style>a{}</style><body></body></html>', screen_only=True)
    assert '@media screen{' in out
    assert '@media print{.cn-hdr{display:none!important}}' in out


def test_script_and_ids_untouched():
    page = '<html><style>a{}</style><body><button id="sign"></button><script>var a=1;</script></body></html>'
    out = apply_theme(page)
    assert '<button id="sign"></button><script>var a=1;</script>' in out
