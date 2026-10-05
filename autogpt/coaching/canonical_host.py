"""Send browsers that open the app on its raw Cloud Run address to the public address.

On the *.run.app address the admin cookie works but writes fail (the origin guard sees http behind the proxy), so
the app is only meant to be used on https://app.changenavigator.co.il.

Rules, kept narrow on purpose:
- only GET and HEAD, so POSTs, webhooks and the scheduler are never redirected;
- only /admin, /login, /dashboard and /register (and below), so /health and the APIs are untouched;
- only when the Host is a *.run.app address AND no X-Forwarded-Host is present. Firebase Hosting forwards the
  original host in X-Forwarded-Host while its own Host is the run.app address, so requests that came through the
  public domain are left alone and cannot loop. A forged header can only switch the redirect off for that request;
- the target is the constant below, never taken from a header;
- CANONICAL_REDIRECT=off in the environment turns it off without a deploy of new code.
"""
from __future__ import annotations

import os
from urllib.parse import quote

CANONICAL_ORIGIN = "https://app.changenavigator.co.il"
PREFIXES = ("/admin", "/login", "/dashboard", "/register")


def _on_prefix(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PREFIXES)


class CanonicalHostMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") in ("GET", "HEAD") and _on_prefix(scope.get("path", "")) \
                and os.getenv("CANONICAL_REDIRECT", "on").lower() != "off":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            host = headers.get("host", "").split(":")[0].lower()
            if host.endswith(".run.app") and "x-forwarded-host" not in headers:
                location = CANONICAL_ORIGIN + quote(scope["path"], safe="/%:@!$&'()*+,;=-._~")
                query = scope.get("query_string", b"").decode("latin-1")
                if query:
                    location += "?" + query
                await send({"type": "http.response.start", "status": 308,
                            "headers": [(b"location", location.encode("latin-1")), (b"content-length", b"0"),
                                        (b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": b""})
                return
        await self.app(scope, receive, send)
