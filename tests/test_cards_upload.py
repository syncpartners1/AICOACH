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


HE_MASTER_PNG = None


def _he_master_png():
    global HE_MASTER_PNG
    if HE_MASTER_PNG is None:
        HE_MASTER_PNG = _png(750, 1125)
    return HE_MASTER_PNG


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
    assert cu._check_png(_he_png(), "he") == (615, 1028)         # stored trimmed size
    assert cu._check_png(_he_master_png(), "he") == (750, 1125)  # print master input
    assert cu._check_png(_png(750, 1125), "en") == (750, 1125)


def test_check_png_rejects_swapped_deck_dimensions():
    # The Hebrew trimmed size is not a valid ENGLISH upload (EN stores 750x1125).
    with pytest.raises(ValueError, match="dimensions"):
        cu._check_png(_png(615, 1028), "en")


def test_check_png_rejects_unknown_hebrew_dimensions():
    # Neither the stored trimmed size nor the print master: reject.
    with pytest.raises(ValueError, match="dimensions"):
        cu._check_png(_png(800, 1200), "he")


def test_derive_he_master_matches_literal_transform():
    """In-module derivation equals the approved literal transform byte-for-byte."""
    import hashlib
    master = _he_master_png()
    literal = Image.open(io.BytesIO(master)).convert("RGB").crop((67, 48, 682, 1076))
    buf = io.BytesIO()
    literal.save(buf, "PNG", optimize=True)
    derived = cu._derive_he_master(master)
    assert hashlib.sha256(derived).hexdigest() == hashlib.sha256(buf.getvalue()).hexdigest()
    with Image.open(io.BytesIO(derived)) as im:
        assert im.size == (615, 1028)
        assert im.mode == "RGB"


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
        self.rewrite_calls = []
        self.deleted = []

    def install(self, monkeypatch):
        monkeypatch.setattr(cu, "_mint_put_url", lambda key: f"https://signed/{key}")
        monkeypatch.setattr(cu, "_head_staging", self.head)
        monkeypatch.setattr(cu, "_staging_bytes", self.read)
        monkeypatch.setattr(cu, "_live_generation", lambda dest: self.live_generation)
        monkeypatch.setattr(cu, "_promote_copy", self.copy)
        monkeypatch.setattr(cu, "_rewrite_staging", self.rewrite)
        monkeypatch.setattr(cu, "_delete_staging", self.delete)

    def head(self, key):
        if self.staged is None:
            return None
        return self.generation, len(self.staged)

    def read(self, key, generation):
        assert generation == self.generation
        return self.staged

    def rewrite(self, key, data, generation):
        from google.api_core.exceptions import PreconditionFailed
        if generation != self.generation:
            raise PreconditionFailed("412 stale generation")
        self.rewrite_calls.append(dict(key=key, size=len(data)))
        self.staged = data
        self.generation += 1
        return self.generation

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


def test_validate_derives_hebrew_master_and_rewrites_staging(monkeypatch):
    store = FakeStore(_he_master_png())
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    ticket, gen = cu._validate_intent(intent_token)
    assert store.rewrite_calls  # master derived, staging rewritten
    assert gen == 101           # ticket pins the REWRITTEN generation
    with Image.open(io.BytesIO(store.staged)) as im:
        assert im.size == (615, 1028)
    import hashlib
    assert hashlib.sha256(store.staged).hexdigest() == hashlib.sha256(
        cu._derive_he_master(_he_master_png())).hexdigest()
    dest, _ = cu._promote_intent(ticket)
    assert store.promote_calls[0]["source_generation"] == 101


def test_validate_rewrite_conflict_fails_closed_no_ticket_no_delete(monkeypatch):
    """A signed-URL replay lands between our read and our rewrite: 409, the newer
    staged bytes are left untouched, and no promote ticket is issued."""
    store = FakeStore(_he_master_png())
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    replay_bytes = _png(750, 1125)
    original_read = store.read
    def read_then_replay(key, generation):
        data = original_read(key, generation)
        store.generation = 101   # replay overwrites staging after our read
        store.staged = replay_bytes
        return data
    monkeypatch.setattr(cu, "_staging_bytes", read_then_replay)
    with pytest.raises(HTTPException) as e:
        cu._validate_intent(intent_token)
    assert e.value.status_code == 409
    assert not store.rewrite_calls      # pinned generation mismatch: nothing written
    assert store.staged is replay_bytes  # newer object preserved
    assert not store.deleted             # and NOT deleted
    assert not store.promote_calls


def test_validate_prederived_hebrew_passthrough_no_double_crop(monkeypatch):
    original = _he_png()
    store = FakeStore(original)
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("he", "1F")
    ticket, gen = cu._validate_intent(intent_token)
    assert not store.rewrite_calls  # already trimmed: untouched, no double crop
    assert gen == 100
    assert store.staged is original
    dest, _ = cu._promote_intent(ticket)
    assert store.promote_calls[0]["source_generation"] == 100


def test_validate_english_master_passthrough_no_rewrite(monkeypatch):
    original = _png(750, 1125)
    store = FakeStore(original)
    store.install(monkeypatch)
    intent_token, _ = cu._create_intent("en", "27F")
    ticket, gen = cu._validate_intent(intent_token)
    assert not store.rewrite_calls
    assert gen == 100
    assert store.staged is original
    cu._promote_intent(ticket)
    assert store.promote_calls[0]["dest"] == "cards-en/27F.png"


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
