"""Regression tests for API-key detection.

These guard the #1 student-reported bug: a valid API key was ignored and the
app silently fell back to "demo mode" because the service read a different
env-var name than the one students fill in (.env.example / Settings page).
"""
import importlib

import services.kie_ai as kie_ai
import services.openai_chat as openai_chat
import services.getlate as getlate


def _clear(monkeypatch, *names):
    for n in names:
        monkeypatch.delenv(n, raising=False)


# ---------------------------------------------------------------------------
# Kie.ai — students set KIE_AI_API_KEY (matches .env.example + Settings page)
# ---------------------------------------------------------------------------
def test_kie_headers_use_kie_ai_api_key(monkeypatch):
    _clear(monkeypatch, "KIE_API_KEY")
    monkeypatch.setenv("KIE_AI_API_KEY", "kie-real-key")
    headers = kie_ai._get_headers()
    assert headers is not None, "valid KIE_AI_API_KEY must NOT fall back to demo mode"
    assert headers["Authorization"] == "Bearer kie-real-key"


def test_kie_headers_legacy_name_still_works(monkeypatch):
    _clear(monkeypatch, "KIE_AI_API_KEY")
    monkeypatch.setenv("KIE_API_KEY", "kie-legacy-key")
    headers = kie_ai._get_headers()
    assert headers is not None
    assert headers["Authorization"] == "Bearer kie-legacy-key"


def test_kie_headers_none_when_unset(monkeypatch):
    _clear(monkeypatch, "KIE_AI_API_KEY", "KIE_API_KEY")
    assert kie_ai._get_headers() is None


# ---------------------------------------------------------------------------
# Jackie — an OpenRouter key must work even if CHAT_PROVIDER defaults to openai
# ---------------------------------------------------------------------------
def test_openrouter_key_routes_via_openrouter_despite_openai_provider(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-v1-studentkey")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client, model = openai_chat.get_ai_client()
    assert client is not None
    assert "openrouter.ai" in str(client.base_url)


def test_falls_back_to_openrouter_key_when_openai_empty(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-fallback")
    client, model = openai_chat.get_ai_client()
    assert client is not None
    assert "openrouter.ai" in str(client.base_url)


def test_real_openai_key_still_uses_openai(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-realopenaikey")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client, model = openai_chat.get_ai_client()
    assert client is not None
    assert "openrouter.ai" not in str(client.base_url)


# ---------------------------------------------------------------------------
# GetLate/Zernio publishing — Paul's bug: posts went out as DRAFT, as JSON,
# and without the image. Root causes: no accountId, wrong media key, no
# publishNow flag, and the env-var name students fill in was ignored.
# ---------------------------------------------------------------------------
class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_getlate_headers_use_zernio_api_key(monkeypatch):
    """Students set ZERNIO_API_KEY (it's what .env.example lists)."""
    monkeypatch.delenv("GETLATE_API_KEY", raising=False)
    monkeypatch.setenv("ZERNIO_API_KEY", "zernio-real-key")
    headers = getlate._get_headers()
    assert headers is not None, "valid ZERNIO_API_KEY must NOT fall back to demo publish"
    assert headers["Authorization"] == "Bearer zernio-real-key"


def test_publish_payload_is_real_post_with_image(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "zernio-real-key")
    monkeypatch.setattr(
        getlate, "get_connected_accounts",
        lambda *a, **k: [{"platform": "linkedin", "_id": "li_123"}],
    )
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp({"id": "post_999"})

    monkeypatch.setattr(getlate.requests, "post", fake_post)

    result = getlate.publish_post(
        {"script": "Hello LinkedIn", "image_url": "https://img/x.png"},
        platforms=["linkedin"],
    )

    body = captured["body"]
    assert body["publishNow"] is True, "must publish now, not save as draft"
    assert body["platforms"] == [{"platform": "linkedin", "accountId": "li_123"}]
    assert body["mediaItems"] == [{"type": "image", "url": "https://img/x.png"}]
    assert "media" not in body, "old wrong key dropped the image"
    assert result["status"] == "published"
    assert result["post_id"] == "post_999"


def test_publish_scheduled_uses_scheduledfor(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "zernio-real-key")
    monkeypatch.setattr(
        getlate, "get_connected_accounts",
        lambda *a, **k: [{"platform": "linkedin", "_id": "li_123"}],
    )
    captured = {}
    monkeypatch.setattr(
        getlate.requests, "post",
        lambda url, headers=None, json=None, timeout=None: (
            captured.update(body=json) or _FakeResp({"id": "p1"})
        ),
    )
    getlate.publish_post(
        {"script": "later", "scheduled_at": "2026-06-01T10:00"},
        platforms=["linkedin"],
    )
    assert "scheduledFor" in captured["body"]
    assert captured["body"].get("publishNow") is not True


# ---------------------------------------------------------------------------
# GPT Image-2 — swapped in for Nano Banana for realistic images, and the
# headshot must flow through the image-to-image model.
# ---------------------------------------------------------------------------
def _fake_kie(monkeypatch, captured):
    import json as _json
    monkeypatch.setenv("KIE_AI_API_KEY", "kie-real-key")
    monkeypatch.setattr(kie_ai.time, "sleep", lambda *a, **k: None)

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _FakeResp({"code": 200, "data": {"taskId": "t_1"}})

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp({"data": {
            "state": "success",
            "resultJson": _json.dumps({"resultUrls": ["https://img/out.png"]}),
        }})

    monkeypatch.setattr(kie_ai.requests, "post", fake_post)
    monkeypatch.setattr(kie_ai.requests, "get", fake_get)


def test_gpt_image2_text_to_image_payload(monkeypatch):
    captured = {}
    _fake_kie(monkeypatch, captured)
    result = kie_ai.generate_image("a coffee shop owner at work")
    body = captured["body"]
    assert body["model"] == "gpt-image-2-text-to-image"
    assert "input_urls" not in body["input"]
    assert body["input"]["aspect_ratio"] == "9:16"
    assert "Ultra-realistic" in body["input"]["prompt"], "realism directive must be applied"
    assert result["image_url"] == "https://img/out.png"
    assert result["demo"] is False


def test_gpt_image2_image_to_image_uses_headshot(monkeypatch):
    captured = {}
    _fake_kie(monkeypatch, captured)
    kie_ai.generate_image(
        "presenting at a conference",
        reference_image_url="https://cdn/headshot.jpg",
    )
    body = captured["body"]
    assert body["model"] == "gpt-image-2-image-to-image"
    assert body["input"]["input_urls"] == ["https://cdn/headshot.jpg"]
    assert "image_input" not in body["input"], "old Nano Banana key must be gone"
    assert "nano-banana" not in str(body)
    assert "reference photo" in body["input"]["prompt"]


def test_kie_headers_strip_pasted_bearer_prefix(monkeypatch):
    """A pasted 'Bearer <key>' must not become 'Bearer Bearer <key>'."""
    _clear(monkeypatch, "KIE_API_KEY")
    monkeypatch.setenv("KIE_AI_API_KEY", "Bearer kie-real-key")
    headers = kie_ai._get_headers()
    assert headers["Authorization"] == "Bearer kie-real-key"
