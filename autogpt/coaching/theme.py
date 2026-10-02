"""Shared look for server-rendered screens that have no styling of their own.

apply_theme() post-processes a finished HTML page: it adds the Change Navigator
theme after the page's own <style> block (so the shared look wins) and a header
bar with the logo. Page markup, element ids and scripts are not touched.
"""
LOGO_URL = "/static/android-chrome-192x192.png"
BRAND_NAME = "Change Navigator"

_THEME_RULES = (
    "body{background:#f0f4f8;color:#1a2b4a;"
    "font-family:'Noto Sans Hebrew',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}"
    ".cn-hdr{background:#1a2b4a;color:#fff;display:flex;align-items:center;gap:12px;"
    "padding:12px 20px;border-radius:12px;margin:0 0 18px;font-weight:700;font-size:17px}"
    ".cn-hdr img{width:32px;height:32px;border-radius:8px}"
    "h1,h2{color:#1a2b4a}a{color:#243d6b}"
    "section{background:#fff;border-radius:12px;padding:16px}"
    ".notice{background:#e0e7ff;color:#1a2b4a;border-radius:10px}"
    "button{background:#1a2b4a;color:#fff;border:0;border-radius:8px;padding:10px 18px;"
    "cursor:pointer;font:inherit}button:disabled{opacity:.6}"
    "input,select,textarea{border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#111827}"
)
_PRINT_RULES = ".cn-hdr{display:none!important}"

_HEADER = (
    f'<div class="cn-hdr"><img src="{LOGO_URL}" alt="">'
    f"<span>{BRAND_NAME}</span></div>"
)


def theme_css(screen_only: bool = False) -> str:
    if screen_only:
        return "@media screen{" + _THEME_RULES + "}@media print{" + _PRINT_RULES + "}"
    return _THEME_RULES


def apply_theme(page: str, *, screen_only: bool = False) -> str:
    """Return page with the shared theme and header added. Safe to call twice.

    screen_only keeps print and PDF output as it was: the theme sits inside
    @media screen and the header is hidden when printing.
    """
    if 'id="cn-theme"' in page:
        return page
    style = f'<style id="cn-theme">{theme_css(screen_only)}</style>'
    if "</style>" in page:
        page = page.replace("</style>", "</style>" + style, 1)
    elif "</head>" in page:
        page = page.replace("</head>", style + "</head>", 1)
    elif '<meta charset="utf-8">' in page:
        page = page.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + style, 1)
    else:
        page = style + page
    if "<body>" in page:
        return page.replace("<body>", "<body>" + _HEADER, 1)
    return page.replace(style, style + _HEADER, 1)
