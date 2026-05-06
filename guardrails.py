"""Input and output guardrails for the Agents SDK graph."""

from __future__ import annotations

import json
import re

from agents import (
    Agent,
    GuardrailFunctionOutput,
    Runner,
    input_guardrail,
    output_guardrail,
)

from config import build_model
from prompts import INPUT_SAFETY_INSTRUCTIONS, OUTPUT_SAFETY_INSTRUCTIONS
from schemas import SafetyCheck


_BAD_INPUT_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bDROP\s+TABLE\b",
    r"<script\b",
    r"\bsteal\s+(password|token|credential)s?\b",
    r"\bkeylogger\b",
    r"\bransomware\b",
]

_POLITICAL_PATTERNS = [
    r"\b(election|politic|politician|party|vote|government|geopolitic)\b",
    r"בחירות",
    r"פוליט",
    r"ממשלה",
    r"מפלג",
    r"לתמוך",
]


def check_input_deterministic(user_text: str) -> str:
    """Fast local input validation before any LLM call."""
    text = (user_text or "").strip()
    if not text:
        return "Input is empty."
    if len(text) > 2000:
        return "Input is too long."
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
        return "Input contains unsupported control characters."
    for pattern in _BAD_INPUT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return f"Input matched blocked pattern: {pattern}"
    for pattern in _POLITICAL_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return f"Input matched political safety boundary: {pattern}"
    return ""


def _looks_ambiguous_for_safety(text: str) -> bool:
    lowered = text.lower()
    sensitive_terms = (
        "hack",
        "exploit",
        "payload",
        "password",
        "token",
        "election",
        "political",
        "illegal",
    )
    return any(term in lowered for term in sensitive_terms)


def check_output_deterministic(output_text: str) -> str:
    """Fast local output validation after the final answer is produced."""
    text = (output_text or "").strip()
    if not text:
        return "Output is empty."

    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and {"intent", "parameters", "confidence"} <= set(data):
            return "Router JSON leaked as final output."

    blocked_terms = ("keylogger", "ransomware", "steal passwords", "bypass authentication")
    lowered = text.lower()
    for term in blocked_terms:
        if term in lowered:
            return f"Output contains blocked term: {term}"

    return ""


_INPUT_SAFETY_AGENT: Agent | None = None
_OUTPUT_SAFETY_AGENT: Agent | None = None


def _input_safety_agent() -> Agent:
    global _INPUT_SAFETY_AGENT
    if _INPUT_SAFETY_AGENT is None:
        model, _ = build_model()
        _INPUT_SAFETY_AGENT = Agent(
            name="Input Safety Guardrail Agent",
            instructions=INPUT_SAFETY_INSTRUCTIONS,
            model=model,
            output_type=SafetyCheck,
        )
    return _INPUT_SAFETY_AGENT


def _output_safety_agent() -> Agent:
    global _OUTPUT_SAFETY_AGENT
    if _OUTPUT_SAFETY_AGENT is None:
        model, _ = build_model()
        _OUTPUT_SAFETY_AGENT = Agent(
            name="Output Safety Guardrail Agent",
            instructions=OUTPUT_SAFETY_INSTRUCTIONS,
            model=model,
            output_type=SafetyCheck,
        )
    return _OUTPUT_SAFETY_AGENT


@input_guardrail
async def input_safety_guardrail(ctx, agent, message):
    """SDK input guardrail: blocks political and harmful requests."""
    deterministic_error = check_input_deterministic(str(message))
    if deterministic_error:
        return GuardrailFunctionOutput(
            output_info={"reason": deterministic_error},
            tripwire_triggered=True,
        )

    text = str(message)
    if not _looks_ambiguous_for_safety(text):
        return GuardrailFunctionOutput(
            output_info={"reason": "Deterministic input guardrail allowed clearly safe request."},
            tripwire_triggered=False,
        )

    result = await Runner.run(_input_safety_agent(), text, context=ctx.context)
    verdict = result.final_output
    is_unsafe = isinstance(verdict, SafetyCheck) and verdict.is_unsafe
    return GuardrailFunctionOutput(
        output_info={"verdict": verdict.model_dump() if isinstance(verdict, SafetyCheck) else str(verdict)},
        tripwire_triggered=is_unsafe,
    )


@output_guardrail
async def output_safety_guardrail(ctx, agent, output):
    """SDK output guardrail: blocks harmful output and leaked router JSON."""
    text = str(output)
    deterministic_error = check_output_deterministic(text)
    if deterministic_error:
        return GuardrailFunctionOutput(
            output_info={"reason": deterministic_error},
            tripwire_triggered=True,
        )

    if not _looks_ambiguous_for_safety(text):
        return GuardrailFunctionOutput(
            output_info={"reason": "Deterministic output guardrail allowed clearly safe output."},
            tripwire_triggered=False,
        )

    result = await Runner.run(_output_safety_agent(), text, context=ctx.context)
    verdict = result.final_output
    is_unsafe = isinstance(verdict, SafetyCheck) and verdict.is_unsafe
    return GuardrailFunctionOutput(
        output_info={"verdict": verdict.model_dump() if isinstance(verdict, SafetyCheck) else str(verdict)},
        tripwire_triggered=is_unsafe,
    )
