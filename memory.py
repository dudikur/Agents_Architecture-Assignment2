"""Persistent conversation history for Assignment 2."""

from __future__ import annotations

import json
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent / "history.json"


def history_exists() -> bool:
    return HISTORY_PATH.is_file()


def load_messages() -> list[dict[str, str]]:
    if not HISTORY_PATH.is_file():
        return []
    try:
        raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    messages = raw.get("messages", [])
    if not isinstance(messages, list):
        return []

    clean: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content is not None:
            clean.append({"role": str(role), "content": str(content)})
    return clean


def save_messages(messages: list[dict[str, str]]) -> None:
    if not messages:
        clear_history_file()
        return
    HISTORY_PATH.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_history_file() -> None:
    if HISTORY_PATH.is_file():
        HISTORY_PATH.unlink()
