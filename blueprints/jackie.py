"""Jackie AI assistant — full-page chat interface (text + live voice)."""
import os
import requests
from flask import Blueprint, render_template, request, jsonify
from auth import login_required
from services.openai_chat import (
    jackie_chat,
    JACKIE_VOICE_INSTRUCTIONS,
    get_realtime_openai_key,
)

jackie_bp = Blueprint("jackie", __name__)

# GA Realtime model. The Beta models (gpt-4o-*-realtime-preview) and the
# Beta /v1/realtime/sessions endpoint were retired — GA uses "gpt-realtime".
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "shimmer")


@jackie_bp.route("/")
@login_required
def index():
    return render_template("admin/jackie.html")


@jackie_bp.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "Message required"}), 400
    result = jackie_chat(message, history)
    return jsonify(result)


@jackie_bp.route("/api/realtime/session", methods=["POST"])
@login_required
def realtime_session():
    """Mint a short-lived OpenAI Realtime token for the browser.

    The browser never sees the real API key — it gets an ephemeral
    client secret that expires in ~60s and opens the WebSocket itself.
    """
    api_key = get_realtime_openai_key()
    if not api_key:
        return jsonify({
            "error": "Voice needs a real OpenAI API key. Add an OpenAI key "
                     "(not an OpenRouter key) in Settings to enable Jackie's "
                     "voice. Text chat still works without it.",
        }), 503

    try:
        # GA Realtime API: ephemeral keys come from /v1/realtime/client_secrets
        # (the Beta /v1/realtime/sessions endpoint was removed), the session
        # config is wrapped in "session" with a required type, and audio
        # transcription/turn_detection/voice moved under "audio".
        r = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "session": {
                    "type": "realtime",
                    "model": REALTIME_MODEL,
                    "instructions": JACKIE_VOICE_INSTRUCTIONS,
                    "audio": {
                        "input": {
                            "transcription": {"model": "whisper-1"},
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                            },
                        },
                        "output": {"voice": REALTIME_VOICE},
                    },
                },
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        # GA returns the secret at top-level "value"; tolerate the old
        # nested shape too so this keeps working if the API shifts again.
        secret = data.get("value") or data.get("client_secret", {}).get("value")
        if not secret:
            raise ValueError(f"No client secret in response: {data}")
        return jsonify({
            "client_secret": secret,
            "expires_at": data.get("expires_at"),
            "model": REALTIME_MODEL,
        })
    except (requests.exceptions.RequestException, ValueError) as e:
        detail = str(e)[:300]
        if getattr(e, "response", None) is not None:
            detail = e.response.text[:300]
        return jsonify({
            "error": "Could not start voice session. Check that your OpenAI "
                     "key has Realtime API access.",
            "detail": detail,
        }), 502
