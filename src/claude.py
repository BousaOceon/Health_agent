"""Thin Claude wrapper — one place for model ids and the call seam.

Model ids come from settings.yaml (`models:`), so they are config, not magic
strings in src/. `call()` is the single seam the engine goes through, which
makes extraction / Pass 1 mockable in tests (monkeypatch src.claude.call).
"""
import json
import logging

from src.config import ANTHROPIC_API_KEY, settings

log = logging.getLogger(__name__)

_models = settings.get("models", {})
SONNET = _models.get("sonnet", "claude-sonnet-4-6")
HAIKU = _models.get("haiku", "claude-haiku-4-5-20251001")

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def call(prompt: str, *, model: str, max_tokens: int = 8000, system: str = None) -> str:
    """Send one user message, return the text. The seam tests monkeypatch."""
    kwargs = {"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    resp = _get_client().messages.create(**kwargs)
    return resp.content[0].text.strip()


def parse_json(text: str):
    """Parse a JSON response, tolerating ```json fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
