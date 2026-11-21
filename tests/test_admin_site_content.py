"""In-repo tests for the integrated site-content admin module.
Endpoint tests use a fake GitHub client; merge-verification tests drive the
real GitHubContent with a fake transport layer."""
import base64

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from autogpt.coaching import admin_site_content as m


class FakeGitHub:
    """Records calls; simulates the content repo."""

    def __init__(self):
        self.calls = []
        self.files = {"content/index.md": "# בית\n", "content/data.json": '{"a": 1}',
                      "static/uploads/x.png": "PNG"}
        self.prs = {}
        self.next_pr = 41

    async def close(self):
        pass

    async def list_tree(self):
        return "a" * 40, [{"path": p, "type": "blob", "size": len(t)}
                          for p, t in self.files.items()]

    async def main_head(self):
        return "a" * 40

    async def get_file(self, path):
        return self.files[path]

    async def open_draft_pr(self, path, text, title):
        self.calls.append(("open_draft_pr", path, title))
        n = self.next_pr
        self.next_pr += 1
        self.prs[n] = {"path": path, "text": text, "merged": False}
        return {"pr_number": n, "branch": f"draft/x-{n}"}

    async def merge_draft_pr(self, pr_number):
        self.calls.append(("merge_draft_pr", pr_number))
        assert pr_number in self.prs, "unknown PR"
        self.prs[pr_number]["merged"] = True
        return {"merged": True, "pr_number": pr_number}


def make_app(fake, authed=True, origin_ok=True):
    def admin():
        if not authed:
            raise HTTPException(status_code=403)

    def guard():
        if not origin_ok:
            raise HTTPException(status_code=403)

    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[m._admin] = admin
    app.dependency_overrides[m._origin_guard] = guard
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fake(monkeypatch):
    f = FakeGitHub()
    monkeypatch.setattr(m, "_client", lambda: f)
    yield f


# ── guards ───────────────────────────────────────────────────────────────────

def test_reads_require_admin(fake):
    c = make_app(fake, authed=False)
    assert c.get("/admin/site-content/data").status_code == 403
    assert c.get("/admin/site-content/entry", params={"path": "content/index.md"}).status_code == 403
    assert c.get("/admin/site-content").status_code == 403
    assert c.get("/admin/site-content/pin-status").status_code == 403


def test_writes_require_origin_guard(fake):
    c = make_app(fake, origin_ok=False)
    assert c.post("/admin/site-content/draft", json={"path": "content/index.md", "text": "x"}).status_code == 403
    assert c.post("/admin/site-content/publish", json={"pr_number": 41}).status_code == 403


# ── listing ──────────────────────────────────────────────────────────────────

def test_data_lists_only_content_areas_and_marks_binary(fake):
    fake.files["secrets/keys.txt"] = "nope"
    c = make_app(fake)
    d = c.get("/admin/site-content/data").json()
    by_path = {e["path"]: e for e in d["entries"]}
    assert "content/index.md" in by_path and "secrets/keys.txt" not in by_path
    assert by_path["content/index.md"]["editable"] is True
    assert by_path["static/uploads/x.png"]["editable"] is False  # binary: view-only
    assert d["content_head"] == "a" * 40


# ── entry ────────────────────────────────────────────────────────────────────

def test_entry_rejects_binary(fake):
    c = make_app(fake)
    assert c.get("/admin/site-content/entry", params={"path": "static/uploads/x.png"}).status_code == 400


# ── draft ────────────────────────────────────────────────────────────────────

def test_draft_then_publish_roundtrip(fake):
    c = make_app(fake)
    r = c.post("/admin/site-content/draft",
               json={"path": "content/index.md", "text": "# חדש\n", "title": "בית"})
    assert r.status_code == 200, r.text
    pr = r.json()["pr_number"]
    assert fake.prs[pr]["text"] == "# חדש\n"
    r2 = c.post("/admin/site-content/publish", json={"pr_number": pr})
    assert r2.status_code == 200 and fake.prs[pr]["merged"]


def test_draft_rejects_invalid_json_content(fake):
    c = make_app(fake)
    r = c.post("/admin/site-content/draft", json={"path": "content/data.json", "text": "{not json"})
    assert r.status_code == 400
    assert not any(call[0] == "open_draft_pr" for call in fake.calls)


def test_draft_rejects_oversized_and_empty(fake):
    c = make_app(fake)
    assert c.post("/admin/site-content/draft",
                  json={"path": "content/index.md", "text": "x" * (300 * 1024)}).status_code == 400
    assert c.post("/admin/site-content/draft",
                  json={"path": "content/index.md", "text": "   "}).status_code == 400


@pytest.mark.parametrize("bad", ["../etc/passwd", "content/../../x", "Dockerfile", "content\\x.md", ""])
def test_path_allowlist_blocks_escape_and_foreign_paths(fake, bad):
    c = make_app(fake)
    assert c.post("/admin/site-content/draft", json={"path": bad, "text": "x"}).status_code == 400


def test_hebrew_path_inside_allowed_area_accepted(fake):
    fake.files["content/אודות.md"] = "טקסט"
    c = make_app(fake)
    assert c.get("/admin/site-content/entry", params={"path": "content/אודות.md"}).status_code == 200


def test_token_never_leaks(fake, monkeypatch):
    from autogpt.coaching.config import coaching_config
    monkeypatch.setattr(coaching_config, "content_repo_gh_token", "secret-token-xyz")
    monkeypatch.setattr(m, "_settings", lambda: ("secret-token-xyz", "o/r", ""))
    c = make_app(fake)
    for resp in [c.get("/admin/site-content"), c.get("/admin/site-content/data"),
                 c.get("/admin/site-content/pin-status")]:
        assert "secret-token-xyz" not in resp.text


def test_unconfigured_token_fails_closed(monkeypatch):
    from autogpt.coaching.config import coaching_config
    monkeypatch.setattr(coaching_config, "content_repo_gh_token", "")
    c = make_app(FakeGitHub())
    assert c.get("/admin/site-content/data").status_code == 503


# ── merge verification (real GitHubContent, fake transport) ──────────────────

def _gh_with_routes(routes):
    gh = m.GitHubContent("t", "o/r")

    async def fake_req(method, path, **kw):
        return routes[(method, path)]

    gh._req = fake_req
    return gh


GOOD_PR = {"state": "open", "base": {"ref": "main"}, "head": {"ref": "draft/1-x"}}


def test_merge_accepts_module_draft_pr():
    gh = _gh_with_routes({
        ("GET", "/pulls/41"): GOOD_PR,
        ("GET", "/pulls/41/files"): [{"filename": "content/index.md"}],
        ("PUT", "/pulls/41/merge"): {"merged": True},
    })
    import asyncio
    out = asyncio.run(gh.merge_draft_pr(41))
    assert out["merged"] is True


def test_merge_rejects_foreign_or_closed_pr():
    import asyncio
    for pr in [{"state": "closed", "base": {"ref": "main"}, "head": {"ref": "draft/1-x"}},
               {"state": "open", "base": {"ref": "main"}, "head": {"ref": "someone/else"}},
               {"state": "open", "base": {"ref": "dev"}, "head": {"ref": "draft/1-x"}}]:
        gh = _gh_with_routes({("GET", "/pulls/9"): pr})
        with pytest.raises(HTTPException) as e:
            asyncio.run(gh.merge_draft_pr(9))
        assert e.value.status_code == 400


def test_merge_binds_exact_reviewed_head_sha():
    """If the draft branch moved after file verification, GitHub rejects the
    merge rather than merging unreviewed bytes (head-sha binding)."""
    import asyncio

    gh = m.GitHubContent("t", "o/r")
    captured = {}

    async def fake_req(method, path, **kw):
        if path.endswith("/merge"):
            captured.update(kw.get("json") or {})
            return {"merged": True}
        routes = {
            ("GET", "/pulls/41"): {**GOOD_PR, "head": {"ref": "draft/1-x", "sha": "headsha123"}},
            ("GET", "/pulls/41/files"): [{"filename": "content/index.md"}],
        }
        return routes[(method, path)]

    gh._req = fake_req
    out = asyncio.run(gh.merge_draft_pr(41))
    assert out["merged"] is True
    assert captured.get("sha") == "headsha123"
    assert captured.get("merge_method") == "squash"


def test_merge_rejects_draft_with_out_of_allowlist_file():
    import asyncio
    gh = _gh_with_routes({
        ("GET", "/pulls/7"): GOOD_PR,
        ("GET", "/pulls/7/files"): [{"filename": "content/index.md"}, {"filename": "config/deploy.yaml"}],
    })
    with pytest.raises(HTTPException) as e:
        asyncio.run(gh.merge_draft_pr(7))
    assert e.value.status_code == 400
