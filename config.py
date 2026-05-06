"""Model configuration for the OpenAI Agents SDK assignment."""

from __future__ import annotations

import os
from pathlib import Path

from agents import OpenAIChatCompletionsModel
from dotenv import load_dotenv
from openai import AsyncOpenAI


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


_MODEL_CACHE: tuple[OpenAIChatCompletionsModel | str, str] | None = None


def reset_model_cache() -> None:
    """Force re-resolution of the model on the next build_model() call."""
    global _MODEL_CACHE
    _MODEL_CACHE = None


def build_model() -> tuple[OpenAIChatCompletionsModel | str, str]:
    """Return an Agents SDK model object and a display name.

    The result is cached so the same client and model are reused across all
    agents and turns. Caching keeps Gemini free-tier 429s from compounding.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    _MODEL_CACHE = _resolve_model()
    return _MODEL_CACHE


def _resolve_model() -> tuple[OpenAIChatCompletionsModel | str, str]:
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env", override=True)
    load_dotenv(project_dir.parent / "assignment_1" / ".env", override=False)
    load_dotenv(project_dir.parent / "agents" / ".env", override=False)

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")
        client = AsyncOpenAI(
            base_url=os.getenv("GEMINI_BASE_URL", GEMINI_BASE_URL),
            api_key=gemini_key,
        )
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        return (
            OpenAIChatCompletionsModel(model=model_name, openai_client=client),
            f"Gemini/{model_name}",
        )

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")
        client = AsyncOpenAI(
            base_url=os.getenv("GROQ_BASE_URL", GROQ_BASE_URL),
            api_key=groq_key,
        )
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        return (
            OpenAIChatCompletionsModel(model=model_name, openai_client=client),
            f"Groq/{model_name}",
        )

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return model_name, f"OpenAI/{model_name}"

    raise RuntimeError(
        "Set GEMINI_API_KEY (or GOOGLE_API_KEY), GROQ_API_KEY, or OPENAI_API_KEY "
        "in .env before running the app."
    )
