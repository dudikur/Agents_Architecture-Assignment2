"""Structured outputs used by the agents and guardrails."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Intent = Literal["getWeather", "calculateMath", "getExchangeRate", "generalChat"]


class RouterDecision(BaseModel):
    """Structured output required from the router agent."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent = Field(description="The next capability or specialist agent.")
    parameters: "RouterParameters" = Field(
        description="Arguments needed by the selected capability.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classification confidence between 0 and 1.",
    )

    @model_validator(mode="after")
    def validate_expected_parameters(self) -> "RouterDecision":
        if self.intent == "getWeather" and not self.parameters.city.strip():
            raise ValueError("getWeather requires parameters.city")
        if self.intent == "calculateMath" and not self.parameters.expression.strip():
            raise ValueError("calculateMath requires parameters.expression")
        if self.intent == "getExchangeRate" and not self.parameters.currencyCode.strip():
            raise ValueError("getExchangeRate requires parameters.currencyCode")
        return self


class RouterParameters(BaseModel):
    """Strict router parameter object for all supported intents."""

    model_config = ConfigDict(extra="forbid")

    city: str = Field(default="", description="City name for weather requests.")
    expression: str = Field(default="", description="Clean arithmetic expression.")
    currencyCode: str = Field(default="", description="Three-letter ISO currency code.")


class SafetyCheck(BaseModel):
    """Boolean safety/format verdict for guardrail agents."""

    model_config = ConfigDict(extra="forbid")

    is_unsafe: bool = Field(description="True when the input or output must be blocked.")
    reason: str = Field(description="Short explanation for logs.")
