import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def pin_llm_provider(monkeypatch):
    """Tests describe OpenRouter unless they opt in to Ollama; they must not
    depend on what LLM_PROVIDER happens to be in a developer's .env."""
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
