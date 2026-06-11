"""LLM factory: returns a provider-specific chat model instance.

Reads LLM_PROVIDER and LLM_MODEL from the environment (or .env file).
Supported providers: openai, claude, gemini, grok.
"""

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI


load_dotenv()

ModelType = Literal["openai", "claude", "gemini", "grok"]


def get_llm(
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7
        ) -> object:
    """Return a LangChain chat model for the given provider.

    Provider resolution order:
      1. ``provider`` argument
      2. ``LLM_PROVIDER`` env var
      3. Defaults to ``openai``
    """
    # Defensive check: reject model names that are all digits (likely a user error)
    if model and model.isdigit():
        print(f"Warning: Invalid model name '{model}' (numeric). Using provider default.")
        model = None

    if provider == "openai":
        return _openai(model, temperature)
    if provider == "claude":
        return _claude(model, temperature)
    if provider == "gemini":
        return _gemini(model, temperature)
    if provider == "grok":
        return _grok(model, temperature)

    raise ValueError(
        f"Unsupported LLM provider '{provider}'. "
        "Choose from: openai, claude, gemini, grok"
    )


def ask_llm(llm, prompt: str) -> str:
    """Send a plain-text prompt and return the response as a string."""
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return " ".join(parts)
    if isinstance(content, dict):
        return content.get("text", str(content))
    return str(content)


# ---------------------------------------------------------------------------
# Provider builders (adapted from previous/helpers.py)
# ---------------------------------------------------------------------------

def _openai(model: str | None, temperature: float):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set.")
    return ChatOpenAI(
        model=model or "gpt-4o-mini",
        temperature=temperature,
        openai_api_key=api_key,
    )


def _claude(model: str | None, temperature: float):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set.")
    return ChatAnthropic(
        model=model or "claude-3-5-sonnet-20241022",
        temperature=temperature,
        api_key=api_key,
    )


def _gemini(model: str | None, temperature: float):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set.")
    return ChatGoogleGenerativeAI(
        model=model or "gemini-2.0-flash",
        temperature=temperature,
        google_api_key=api_key,
    )


def _grok(model: str | None, temperature: float):
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY not set.")
    return ChatOpenAI(
        model=model or "grok-2",
        temperature=temperature,
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )
