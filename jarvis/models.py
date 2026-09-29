from __future__ import annotations

from jarvis.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


def local_model(temperature: float = 0.2):
    """Tool-calling local model. Qwen3.x is the 2026 default.

    Imported lazily so the map, the bridge, and the tests do not require a model
    provider to be installed.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
    )


def smart_model(temperature: float = 0.2):
    """
    Supervisor brain. Uses a cloud model if a key is present, otherwise local.
    Routing quality matters more than specialist quality, so the smarter model
    goes here.
    """
    if ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=ANTHROPIC_MODEL, temperature=temperature)
    if OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=OPENAI_MODEL, temperature=temperature)
    return local_model(temperature=temperature)
