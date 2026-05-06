"""OpenAI Agents SDK graph for Assignment 2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents import Agent, Runner
from agents.model_settings import ModelSettings

from config import build_model
from guardrails import (
    check_input_deterministic,
    check_output_deterministic,
    input_safety_guardrail,
    output_safety_guardrail,
)
from prompts import (
    CLASSIFIER_INSTRUCTIONS,
    CURRENCY_INSTRUCTIONS,
    GENERAL_CHAT_INSTRUCTIONS,
    MATH_INSTRUCTIONS,
    SAFETY_REFUSAL,
    TRIAGE_INSTRUCTIONS,
    WEATHER_INSTRUCTIONS,
)
from schemas import RouterDecision
from tools import calculate_math, get_exchange_rate, get_weather


@dataclass
class TurnResult:
    """Application-level result for CLI, Gradio, and demo logging."""

    history: list[dict[str, str]]
    reply: str
    router_decision: RouterDecision | None
    structured_router_json: str
    handoff_log: str
    blocked: bool = False
    safety_reason: str = ""


def _agent_name_for_intent(intent: str) -> str:
    return {
        "getWeather": "Weather Agent",
        "calculateMath": "Math Agent",
        "getExchangeRate": "Currency Agent",
        "generalChat": "General Chat Agent",
    }.get(intent, "General Chat Agent")


_GRAPH_CACHE: tuple[Agent, Agent, str] | None = None


def reset_agent_graph_cache() -> None:
    """Force the agent graph to be rebuilt on the next call."""
    global _GRAPH_CACHE
    _GRAPH_CACHE = None


def _build_agent_graph() -> tuple[Agent, Agent, str]:
    """Build (classifier_agent, triage_agent, display_name) once and cache it.

    The Agents SDK objects are reusable across turns, so caching here removes
    redundant model construction and significantly reduces API calls when the
    underlying model is metered (Gemini free tier).
    """
    global _GRAPH_CACHE
    if _GRAPH_CACHE is not None:
        return _GRAPH_CACHE

    model, display_name = build_model()
    required_tool = ModelSettings(tool_choice="required")

    weather_agent = Agent(
        name="Weather Agent",
        instructions=WEATHER_INSTRUCTIONS,
        model=model,
        tools=[get_weather],
        model_settings=required_tool,
        handoff_description="Handle weather and temperature requests for a city.",
    )

    math_agent = Agent(
        name="Math Agent",
        instructions=MATH_INSTRUCTIONS,
        model=model,
        tools=[calculate_math],
        model_settings=required_tool,
        handoff_description="Handle arithmetic and natural-language word problems.",
    )

    currency_agent = Agent(
        name="Currency Agent",
        instructions=CURRENCY_INSTRUCTIONS,
        model=model,
        tools=[get_exchange_rate],
        model_settings=required_tool,
        handoff_description="Handle exchange-rate requests for currencies.",
    )

    general_chat_agent = Agent(
        name="General Chat Agent",
        instructions=GENERAL_CHAT_INSTRUCTIONS,
        model=model,
        handoff_description="Handle safe general conversation and research questions.",
    )

    classifier_agent = Agent(
        name="Classifier Agent",
        instructions=CLASSIFIER_INSTRUCTIONS,
        model=model,
        output_type=RouterDecision,
    )

    triage_agent = Agent(
        name="Triage Agent",
        instructions=TRIAGE_INSTRUCTIONS,
        model=model,
        handoffs=[weather_agent, math_agent, currency_agent, general_chat_agent],
        input_guardrails=[input_safety_guardrail],
        output_guardrails=[output_safety_guardrail],
    )

    _GRAPH_CACHE = (classifier_agent, triage_agent, display_name)
    return _GRAPH_CACHE


def _build_input_list(history: list[dict[str, str]], user_text: str) -> list[dict[str, str]]:
    """Build the SDK input list from prior turns plus the new user message.

    Passing the conversation history as input messages (instead of embedding it
    in the prompt) keeps the natural SDK flow: when the triage agent hands off
    to a specialist (general chat included), the SDK forwards the message list
    so the specialist sees the full context.
    """
    input_list: list[dict[str, str]] = []
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content is not None:
            input_list.append({"role": str(role), "content": str(content)})
    input_list.append({"role": "user", "content": user_text})
    return input_list


async def classify_user_input(user_text: str) -> RouterDecision:
    classifier_agent, _, _ = _build_agent_graph()
    result = await Runner.run(classifier_agent, user_text)
    if not isinstance(result.final_output, RouterDecision):
        raise TypeError("Router agent did not return RouterDecision")
    return result.final_output


async def run_turn(history: list[dict[str, str]], user_text: str) -> TurnResult:
    """Run one user turn through classifier (Part B), triage handoff, and guardrails."""
    user_text = (user_text or "").strip()
    input_error = check_input_deterministic(user_text)
    if input_error:
        new_history = [*history, {"role": "user", "content": user_text}]
        new_history.append({"role": "assistant", "content": SAFETY_REFUSAL})
        return TurnResult(
            history=new_history,
            reply=SAFETY_REFUSAL,
            router_decision=None,
            structured_router_json="{}",
            handoff_log="Input blocked before routing.",
            blocked=True,
            safety_reason=input_error,
        )

    classifier_agent, triage_agent, _ = _build_agent_graph()

    router_result = await Runner.run(classifier_agent, user_text)
    decision = router_result.final_output
    if not isinstance(decision, RouterDecision):
        raise TypeError("Router agent did not return a RouterDecision object.")

    structured_json = decision.model_dump_json(indent=2)
    target_agent = _agent_name_for_intent(decision.intent)
    handoff_log = f"Classifier intent {decision.intent}; expected handoff: {target_agent}"

    triage_input = _build_input_list(history, user_text)

    try:
        triage_result = await Runner.run(triage_agent, triage_input)
        reply = str(triage_result.final_output).strip()
    except Exception as exc:
        if "Guardrail" in exc.__class__.__name__ or "Tripwire" in exc.__class__.__name__:
            reply = SAFETY_REFUSAL
            new_history = [*history, {"role": "user", "content": user_text}]
            new_history.append({"role": "assistant", "content": reply})
            return TurnResult(
                history=new_history,
                reply=reply,
                router_decision=decision,
                structured_router_json=structured_json,
                handoff_log=handoff_log,
                blocked=True,
                safety_reason=str(exc),
            )
        raise

    output_error = check_output_deterministic(reply)
    if output_error:
        reply = SAFETY_REFUSAL
        blocked = True
        safety_reason = output_error
    else:
        blocked = False
        safety_reason = ""

    new_history = [*history, {"role": "user", "content": user_text}]
    new_history.append({"role": "assistant", "content": reply})
    return TurnResult(
        history=new_history,
        reply=reply,
        router_decision=decision,
        structured_router_json=structured_json,
        handoff_log=handoff_log,
        blocked=blocked,
        safety_reason=safety_reason,
    )


def format_turn_log(result: TurnResult) -> str:
    payload: dict[str, Any] = {
        "router_structured_output": json.loads(result.structured_router_json),
        "handoff_log": result.handoff_log,
        "blocked": result.blocked,
        "safety_reason": result.safety_reason,
        "reply": result.reply,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
