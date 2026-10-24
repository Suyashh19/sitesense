"""Optional LLM narration. Uses whichever provider has a key in .env: Gemini (free), Groq (free) or Claude.
The LLM only rewrites computed facts into prose; if no key is set or a call fails, callers fall back to templates.

Check your key with:  python -m app.llm   (from backend/)
"""
import os

import requests

from . import config  # noqa: F401  (loads .env)

PROVIDERS = {
    "gemini": {"key": "GEMINI_API_KEY", "model": "GEMINI_MODEL", "default": "gemini-2.5-flash", "label": "Gemini"},
    "groq": {"key": "GROQ_API_KEY", "model": "GROQ_MODEL", "default": "openai/gpt-oss-120b", "label": "Groq"},
    "anthropic": {"key": "ANTHROPIC_API_KEY", "model": "LLM_MODEL", "default": "claude-opus-5-5", "label": "Claude"},
}


def active_provider() -> str | None:
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced in PROVIDERS and os.getenv(PROVIDERS[forced]["key"]):
        return forced
    return next((p for p, c in PROVIDERS.items() if os.getenv(c["key"])), None)


def provider_label() -> str | None:
    p = active_provider()
    return PROVIDERS[p]["label"] if p else None


def generate(system: str, user: str) -> str | None:
    p = active_provider()
    if not p:
        return None
    cfg = PROVIDERS[p]
    key, model = os.getenv(cfg["key"]), os.getenv(cfg["model"]) or cfg["default"]
    try:
        if p == "gemini":
            return _gemini(key, model, system, user)
        if p == "groq":
            return _groq(key, model, system, user)
        return _anthropic(key, model, system, user)
    except Exception as e:  # noqa: BLE001  never break the briefing because of the LLM
        print(f"LLM ({p}) failed, using template: {e}")
        return None


def _gemini(key: str, model: str, system: str, user: str) -> str | None:
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}]},
        timeout=30,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(x.get("text", "") for x in parts).strip() or None


def _groq(key: str, model: str, system: str, user: str) -> str | None:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip() or None


def _anthropic(key: str, model: str, system: str, user: str) -> str | None:
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=30.0, max_retries=1)
    response = client.beta.messages.create(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        return None
    return next((b.text for b in response.content if b.type == "text"), None)


if __name__ == "__main__":
    p = active_provider()
    if not p:
        print("No LLM key found in .env. Briefings will use templates (this is fine).")
    else:
        print(f"Testing {PROVIDERS[p]['label']} ...")
        out = generate("Reply in one short sentence.", "Say hello to the SiteSense team.")
        print("OK:", out if out else "FAILED (see error above)")
