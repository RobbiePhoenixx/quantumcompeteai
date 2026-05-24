"""Jackie AI — provider-agnostic chat (OpenAI direct or OpenRouter)."""
import os
from openai import OpenAI

JACKIE_SYSTEM_PROMPT = """You are Jackie, a friendly and knowledgeable AI business assistant.
You help small business owners with marketing, operations, customer management, and growth strategy.
Keep responses concise and actionable — 2-4 paragraphs max.
Use a warm, professional tone. You're like a smart friend who happens to know business.
If asked about technical setup, guide them step by step.
Always be encouraging — these are hardworking small business owners."""

# Voice mode is a live spoken conversation, so the personality is the same
# but the delivery has to be short and natural — nobody wants a four-paragraph
# monologue read aloud.
JACKIE_VOICE_INSTRUCTIONS = """You are Jackie, a warm, upbeat AI business assistant having a live VOICE conversation with a small business owner.
Speak naturally, like a smart friend on a phone call. Use contractions.
Keep answers to 1-3 short sentences. If something needs more detail, give the headline first and ask if they want you to go deeper.
Be encouraging and concrete. Don't read lists or markdown aloud — just talk."""


def get_realtime_openai_key():
    """Return a real OpenAI key usable for the Realtime API, or None.

    The Realtime API is OpenAI-only — an OpenRouter key (sk-or-...) cannot
    open a realtime session, so voice degrades gracefully to text-only.
    """
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key and not key.startswith("sk-or-"):
        return key
    return None


def _openrouter_client(api_key):
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={"HTTP-Referer": os.getenv("APP_URL", "http://localhost:8000")},
    ), "google/gemini-2.5-flash"


def get_ai_client():
    """Return (OpenAI client, model_name) based on the configured provider.

    Students often have only an OpenRouter key (or paste it into the OpenAI
    field) while CHAT_PROVIDER defaults to "openai". An OpenRouter key on the
    OpenAI endpoint silently fails, so we auto-detect: any key starting with
    "sk-or-" is routed through OpenRouter regardless of CHAT_PROVIDER, and we
    fall back to whichever key is actually set.
    """
    provider = os.getenv("CHAT_PROVIDER", "openai")
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if provider == "openai":
        # An OpenRouter key pasted into the OpenAI field — route it correctly.
        if openai_key.startswith("sk-or-"):
            return _openrouter_client(openai_key)
        if openai_key:
            return OpenAI(api_key=openai_key), os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        # No OpenAI key but an OpenRouter key is available — use it.
        if openrouter_key:
            return _openrouter_client(openrouter_key)
        return None, None

    # provider == "openrouter"
    key = openrouter_key or (openai_key if openai_key.startswith("sk-or-") else "")
    if not key:
        return None, None
    return _openrouter_client(key)


def jackie_chat(user_message, history=None):
    """Send a message to Jackie and get a response."""
    client, model = get_ai_client()
    if not client:
        return {
            "response": "Jackie is not configured yet. Add your OPENAI_API_KEY or OPENROUTER_API_KEY in Settings to activate me!",
            "provider": "demo",
        }
    messages = [{"role": "system", "content": JACKIE_SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_message})
    try:
        resp = client.chat.completions.create(model=model, messages=messages, max_tokens=1024, temperature=0.4)
        return {"response": resp.choices[0].message.content, "provider": os.getenv("CHAT_PROVIDER", "openrouter")}
    except Exception as e:
        return {"response": f"Sorry, I hit an error: {str(e)}", "provider": "error"}
