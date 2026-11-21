import io
import time

import pytest
from fastapi import HTTPException
from PIL import Image

from autogpt.coaching import cards_upload as cu


def _png(w, h):
    """Real PNG bytes, noisy enough to sit well above the 1KB floor."""
    import os
    buf = io.BytesIO()
    Image.frombytes("RGB", (w, h), os.urandom(w * h * 3)).save(buf, format="PNG")
    return buf.getvalue()


HE_PNG = None  # built lazily; building 4 noisy PNGs at import is wasteful


def _he_png():
    global HE_PNG
    if HE_PNG is None:
        HE_PNG = _png(615, 1028)
    return HE_PNG


# ── target allowlist ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang,stem", [("he", "1F"), ("he", "54B"), ("en", "27F"), ("en", "9B")])
def test_valid_targets_pass(lang, stem):
    cu._valid_target(lang, stem)


@pytest.mark.parametrize("lang,stem", [
    ("he", "0F"), ("he", "55F"), ("he", "1f"), ("he", "1C"), ("he", ""), ("he", "1F.png"),
    ("fr", "1F"), ("", "1F"), ("HE", "1F"), ("he", " 1F"), ("he", "1F "),
])
def test_invalid_targets_rejected(lang, stem):
    with pytest.raises(HTTPException) as e:
        cu._valid_target(lang, stem)
    assert e.value.status_code == 400


# ── decode check ─────────────────────────────────────────────────────────────

def test_check_png_accepts_exact_deck_dimensions():
    cu._check_png(_he_png(), "he")
    cu._check_png(_png(750, 1125), "en")


def test_check_png_rejects_swapped_deck_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        cu._check_png(_png(750, 1125), "he")


def test_check_png_rejects_non_png():
    buf = io.BytesIO()
    Image.new("RGB", (615, 1028)).save(buf, format="JPEG")
    data = buf.getvalue()
    data = data + b"0" * max(0, 1024 - len(data))  # over the size floor, still JPEG
    with pytest.raises(ValueError, match="not a PNG"):
        cu._check_png(data, "he")


def test_check_png_rejects_truncated_png():
    """Must hold even though weasyprint sets PIL LOAD_TRUNCATED_IMAGES=True."""
    data = _he_png()[: len(_he_png()) // 2]
    with pytest.raises(ValueError, match="incomplete PNG"):
        cu._check_png(data, "he")


def test_check_png_rejects_undersized_and_oversized():
    with pytest.raises(ValueError, match="size"):
        cu._check_png(b"\x89PNG" + b"0" * 100, "he")
    with pytest.raises(ValueError, match="size"):
        cu._check_png(b"0" * (5 * 1024 * 1024 + 1), "he")


# ── token flow with a fake storage layer ─────────────────────────────────────

class FakeStore:
    """In-memory stand-in for the storage-facade functions."""

    def __init__(self, staged_bytes):
        self.staged = staged_bytes          # bytes that "the browser uploaded"
        self.generation = 100
        self.live_generation = 7
        self.promote_calls = []
        self.deleted = []

    def install(self, monkeypatch):
        monkeypatch.setattr(cu, "_mint_put_url", lambda key: f"https://signed/{key}")
        monkeypatch.setattr(cu, "_head_staging", self.head)
        monkeypatch.setattr(cu, "_staging_bytes", self.read)
        monkeypatch.setattr(cu, "_live_generation", lambda dest: self.live_generation)
        monkeypatch.setattr(cu, "_promote_copy", self.copy)
        monkeypatch.setattr(cu, "_delete_staging", self.delete)

    def head(self, key):
        if self.staged is None:
            return None
        return self.generation, len(self.staged)

    def read(self, key, generation):
        assert generation == self.generation
        return self.staged

    def copy(self, key, generation, dest, expected_live_generation):
        self.promote_calls.append(
            dict(key=key, source_generation=generation, dest=dest, expected_live=expected_live_generation)
        )
        return 900  # new live generation

    def delete(self, key):
        self.deleted.append(key)
        self.staged = None


def test_happy_path_promotes_validated_bytes_once(monkeypatch):
    store = FakeStore(_he_png())
    store.install(monkeypatch)
    intent_token, url = cu._create_intent("he", "1F")
    payload = cu._read_token(intent_token, "intent")
    assert url.endswith(f"/intent/{payload['key'].split('/')[1]}/he/1F.png")  # intent id bound into the key
    ticket, gen = cu._validate_intent(intent_token)
    assert gen == 100
    dest, new_gen = cu._promote_intent(ticket)
    assert dest == "cards-he/1F.png"
    call = store.promote_calls[0]
    assert call["source_generation"] == 100      # copies exactly the validated bytes
    assert call["expected_live"] == 7            # destination precondition = current live generation
    assert store.deleted  # staging consumed
    with pytest.raises(HTTPException) as e:      # replayed ticket: staging gone -> 409
        cu._promote_intent(ticket)
    assert e.value.status_code == 409


def test_intent_token_cannot_promote_directly(monkeypatch):
    FakeStore(_he_png()).install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    with pytest.raises(HTTPException) as e:
        cu._promote_intent(intent_token)  # wrong token kind
    assert e.value.status_code == 400


def test_tampered_token_rejected(monkeypatch):
    FakeStore(_he_png()).install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    raw, sig = intent_token.rsplit(".", 1)
    with pytest.raises(HTTPException) as e:
        cu._read_token(raw + "." + ("0" if sig[0] != "0" else "1") + sig[1:], "intent")
    assert e.value.status_code == 400


def test_expired_token_rejected(monkeypatch):
    FakeStore(_he_png()).install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    real_time = time.time
    monkeypatch.setattr(cu.time, "time", lambda: real_time() + 700)
    with pytest.raises(HTTPException) as e:
        cu._validate_intent(intent_token)
    assert e.value.status_code == 410


def test_promote_rejects_staging_change_after_validation(monkeypatch):
    """A signed-URL replay overwrote the staging object: promotion must not proceed."""
    store = FakeStore(_he_png())
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    ticket, _ = cu._validate_intent(intent_token)
    store.generation = 101  # replay landed after validation
    with pytest.raises(HTTPException) as e:
        cu._promote_intent(ticket)
    assert e.value.status_code == 409
    assert not store.promote_calls


def test_validate_without_staged_object_fails(monkeypatch):
    FakeStore(None).install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    with pytest.raises(HTTPException) as e:
        cu._validate_intent(intent_token)
    assert e.value.status_code == 400


def test_validate_rejects_bad_image_and_cleans_staging(monkeypatch):
    store = FakeStore(_png(100, 100))
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    with pytest.raises(HTTPException) as e:
        cu._validate_intent(intent_token)
    assert e.value.status_code == 400
    assert store.deleted  # rejected bytes removed immediately
    with pytest.raises(HTTPException) as e2:  # intent token still valid, but nothing staged
        cu._validate_intent(intent_token)
    assert e2.value.status_code == 400


def test_unconfigured_buckets_fail_closed(monkeypatch):
    from autogpt.coaching.config import coaching_config
    monkeypatch.setattr(coaching_config, "cards_staging_bucket", "")
    with pytest.raises(HTTPException) as e:
        cu._create_intent("he", "1F")
    assert e.value.status_code == 503
