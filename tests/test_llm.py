"""Unit tests for autogpt.coaching.llm — Gemini 3.5 Flash migration coverage."""
import base64

import pytest

from autogpt.coaching import llm


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _FakePart:
    def __init__(self, text, thought_signature=None):
        self.text = text
        self.thought_signature = thought_signature


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, parts):
        self.content = _FakeContent(parts)


class _FakeResponse:
    def __init__(self, text="ok", thought_signature=None):
        self.text = text
        parts = [_FakePart(text, thought_signature)]
        self.candidates = [_FakeCandidate(parts)]


class _FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.response


class _FakeClient:
    def __init__(self, response=None):
        self.models = _FakeModels(response or _FakeResponse())


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(llm, "_client", client)
    return client


@pytest.fixture(autouse=True)
def reset_client(monkeypatch):
    yield
    # each test sets its own client via fake_client


# ── Model normalisation ───────────────────────────────────────────────────────

class TestNormalizeModel:
    def test_default_model_is_gemini_2_5_flash(self):
        assert llm.DEFAULT_GEMINI_MODEL == "gemini-2.5-flash"

    def test_claude_name_maps_to_default(self):
        assert llm._normalize_model("claude-sonnet-4-6") == "gemini-2.5-flash"

    def test_non_gemini_name_maps_to_default(self):
        assert llm._normalize_model("gpt-4") == "gemini-2.5-flash"

    def test_gemini_name_passes_through(self):
        assert llm._normalize_model("gemini-2.5-flash") == "gemini-2.5-flash"

    def test_gemini3_detection(self):
        assert llm._is_gemini3("gemini-3.5-flash")
        assert not llm._is_gemini3("gemini-2.5-flash")


# ── Thinking level ────────────────────────────────────────────────────────────

class TestThinkingLevel:
    def test_valid_levels_pass_through(self):
        for level in llm.ALLOWED_THINKING_LEVELS:
            assert llm._normalize_thinking_level(level) == level

    def test_case_insensitive(self):
        assert llm._normalize_thinking_level("HIGH") == "high"

    def test_invalid_falls_back_to_medium(self):
        assert llm._normalize_thinking_level("extreme") == "medium"

    def test_none_falls_back_to_medium(self):
        assert llm._normalize_thinking_level(None) == "medium"


# ── Request construction ──────────────────────────────────────────────────────

class TestRequestConstruction:
    def test_gemini3_uses_thinking_level_not_temperature(self, fake_client):
        llm.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        call = fake_client.models.calls[0]
        assert call["model"] == "gemini-3.5-flash"
        assert call["config"].thinking_config.thinking_level.value.lower() == "medium"
        assert call["config"].temperature is None

    def test_thinking_level_override(self, fake_client):
        llm.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="gemini-3.5-flash",
            temperature=0.0,
            thinking_level="low",
        )
        assert fake_client.models.calls[0]["config"].thinking_config.thinking_level.value.lower() == "low"

    def test_legacy_model_keeps_temperature_and_no_thinking_config(self, fake_client):
        llm.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="gemini-2.5-flash",
            temperature=0.7,
        )
        call = fake_client.models.calls[0]
        assert call["config"].temperature == 0.7
        assert call["config"].thinking_config is None

    def test_system_prompt_mapped_to_system_instruction(self, fake_client):
        llm.chat_completion(
            [
                {"role": "system", "content": "You are a coach."},
                {"role": "user", "content": "hi"},
            ],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        call = fake_client.models.calls[0]
        assert call["config"].system_instruction == "You are a coach."
        assert all(t["role"] != "system" for t in call["contents"])

    def test_empty_messages_get_placeholder_turn(self, fake_client):
        llm.chat_completion([], model="gemini-3.5-flash", temperature=0.7)
        contents = fake_client.models.calls[0]["contents"]
        assert contents == [{"role": "user", "parts": [{"text": "Hello"}]}]


# ── Thought signatures ────────────────────────────────────────────────────────

class TestThoughtSignatures:
    def test_response_signature_returned_base64(self, monkeypatch):
        client = _FakeClient(_FakeResponse("reply", thought_signature=b"sig-bytes"))
        monkeypatch.setattr(llm, "_client", client)
        result = llm.chat_completion_with_metadata(
            [{"role": "user", "content": "hi"}],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        assert result.text == "reply"
        assert result.thought_signature == base64.b64encode(b"sig-bytes").decode("ascii")

    def test_history_signature_reattached_to_model_turn(self, fake_client):
        sig_b64 = base64.b64encode(b"sig-bytes").decode("ascii")
        llm.chat_completion(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there", "thought_signature": sig_b64},
                {"role": "user", "content": "follow up"},
            ],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        contents = fake_client.models.calls[0]["contents"]
        model_turn = contents[1]
        assert model_turn["role"] == "model"
        assert model_turn["parts"][0]["thought_signature"] == b"sig-bytes"
        # user turns never carry signatures
        assert "thought_signature" not in contents[0]["parts"][0]

    def test_bad_signature_dropped_not_fatal(self, fake_client):
        reply = llm.chat_completion(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi", "thought_signature": "!!!not-base64!!!"},
                {"role": "user", "content": "again"},
            ],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        assert reply == "ok"
        model_turn = fake_client.models.calls[0]["contents"][1]
        assert "thought_signature" not in model_turn["parts"][0]

    def test_no_signature_in_response_gives_none(self, fake_client):
        result = llm.chat_completion_with_metadata(
            [{"role": "user", "content": "hi"}],
            model="gemini-3.5-flash",
            temperature=0.7,
        )
        assert result.thought_signature is None


# ── Legacy fallback guard ─────────────────────────────────────────────────────

class TestLegacyFallback:
    def test_gemini3_on_legacy_client_raises_clear_error(self, monkeypatch):
        class _LegacyOnlyClient:
            pass  # no .models.generate_content

        monkeypatch.setattr(llm, "_client", _LegacyOnlyClient())
        with pytest.raises(Exception, match="google-genai SDK"):
            llm.chat_completion(
                [{"role": "user", "content": "hi"}],
                model="gemini-3.5-flash",
                temperature=0.7,
            )
