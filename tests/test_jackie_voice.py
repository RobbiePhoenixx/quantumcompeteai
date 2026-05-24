"""Tests for Jackie's live-voice (OpenAI Realtime) session endpoint.

The browser must never receive the real API key — it gets a short-lived
ephemeral token. Voice is OpenAI-only, so an OpenRouter key must degrade
gracefully (text chat keeps working).
"""
import blueprints.jackie as jackie_bp_mod


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = ""

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_realtime_session_requires_auth(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-real")
    resp = client.post("/jackie/api/realtime/session")
    assert resp.status_code == 302  # redirected to login


def test_realtime_session_no_openai_key(auth_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = auth_client.post("/jackie/api/realtime/session")
    assert resp.status_code == 503
    assert "OpenAI" in resp.get_json()["error"]


def test_realtime_session_rejects_openrouter_key(auth_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-v1-routerkey")
    resp = auth_client.post("/jackie/api/realtime/session")
    assert resp.status_code == 503, "OpenRouter key cannot open a Realtime session"


def test_realtime_session_mints_ephemeral_token(auth_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-realkey")
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["auth"] = headers.get("Authorization")
        sent["body"] = json
        # GA returns the ephemeral key at top-level "value".
        return _FakeResp({"value": "ek_ephemeral_123", "expires_at": 1999999999})

    monkeypatch.setattr(jackie_bp_mod.requests, "post", fake_post)

    resp = auth_client.post("/jackie/api/realtime/session")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["client_secret"] == "ek_ephemeral_123"
    assert "realtime" in data["model"]
    # The real key went to OpenAI, never to the browser.
    assert sent["auth"] == "Bearer sk-proj-realkey"
    # GA endpoint + GA session shape (not the retired /v1/realtime/sessions).
    assert sent["url"].endswith("/v1/realtime/client_secrets")
    session = sent["body"]["session"]
    assert session["type"] == "realtime"
    assert session["audio"]["output"]["voice"]
    assert "Jackie" in session["instructions"]


def test_realtime_session_handles_legacy_nested_secret(auth_client, monkeypatch):
    """Be tolerant if the API returns the old client_secret.value shape."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-realkey")
    monkeypatch.setattr(
        jackie_bp_mod.requests, "post",
        lambda *a, **k: _FakeResp({"client_secret": {"value": "ek_nested_9"}}),
    )
    resp = auth_client.post("/jackie/api/realtime/session")
    assert resp.status_code == 200
    assert resp.get_json()["client_secret"] == "ek_nested_9"
