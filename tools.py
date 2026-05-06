"""Deterministic tools used by the OpenAI Agents SDK agents."""

from __future__ import annotations

import ast
import operator

import requests
from agents import function_tool

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_FRANKFURTER_LATEST = "https://api.frankfurter.app/latest"

_WMO_HE: dict[int, str] = {
    0: "בהיר",
    1: "ברור ברובו",
    2: "מעונן חלקית",
    3: "מעונן",
    45: "ערפל",
    48: "ערפל קפוא",
    51: "טפטוף קל",
    53: "טפטוף",
    55: "טפטוף כבד",
    56: "טפטוף קפוא",
    57: "טפטוף קפוא כבד",
    61: "גשם קל",
    63: "גשם",
    65: "גשם כבד",
    66: "גשם מקורר",
    67: "גשם מקורר כבד",
    71: "שלג קל",
    73: "שלג",
    75: "שלג כבד",
    77: "גרגירי שלג",
    80: "ממטרים קלים",
    81: "ממטרים",
    82: "ממטרים כבדים",
    85: "ממטרי שלג",
    86: "ממטרי שלג כבדים",
    95: "סופת רעמים",
    96: "סופת רעמים עם ברד קל",
    99: "סופת רעמים עם ברד כבד",
}

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _wmo_label(code: int | None) -> str:
    if code is None:
        return "לא ידוע"
    return _WMO_HE.get(int(code), "תנאים מעורבבים")


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("Only numbers are allowed in the expression.")

    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Division by zero is not allowed.")
        return float(_ALLOWED_BINOPS[type(node.op)](left, right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return float(_ALLOWED_UNARY[type(node.op)](_eval_ast(node.operand)))

    raise ValueError("The expression contains an unsupported operation.")


def _calculate(expression: str) -> str:
    text = (expression or "").strip()
    if not text:
        return "No mathematical expression was provided."

    try:
        tree = ast.parse(text, mode="eval")
        value = _eval_ast(tree.body)
    except SyntaxError:
        return "The mathematical expression is invalid."
    except ValueError as exc:
        return str(exc)

    if value == int(value):
        return str(int(value))
    return f"{value:.6g}"


_FX_ALIASES: dict[str, str] = {
    "DOLLAR": "USD",
    "USD": "USD",
    "דולר": "USD",
    "EURO": "EUR",
    "EUR": "EUR",
    "יורו": "EUR",
    "POUND": "GBP",
    "GBP": "GBP",
    "FUNT": "GBP",
    "פאונד": "GBP",
    "ליש": "GBP",
    "ין": "JPY",
    "YEN": "JPY",
}
_FX_SNIFF_ORDER = ("USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "CNY")


def _normalize_fx_code(currency_code: str) -> str:
    raw = (currency_code or "").strip()
    if not raw:
        return ""

    if raw in _FX_ALIASES:
        return _FX_ALIASES[raw]

    upper = raw.upper()
    if upper in _FX_ALIASES:
        return _FX_ALIASES[upper]

    if len(upper) == 3 and upper.isalpha():
        return upper

    for iso in _FX_SNIFF_ORDER:
        if iso in upper:
            return iso

    return upper[:3] if len(upper) >= 3 else upper


@function_tool
def calculate_math(expression: str) -> str:
    """Evaluate a clean arithmetic expression deterministically."""
    result = _calculate(expression)
    return f"expression={expression}; result={result}"


@function_tool
def get_exchange_rate(currencyCode: str) -> str:
    """Return the latest exchange rate from the given currency to ILS."""
    raw_in = (currencyCode or "").strip()
    if "שקל" in raw_in or "ש״ח" in raw_in or "ILS" in raw_in.upper():
        return "ILS is the local target currency. Choose a foreign currency such as USD, EUR, or GBP."

    code = _normalize_fx_code(raw_in)
    if not code or len(code) != 3 or not code.isalpha():
        return (
            f"Could not identify a valid currency code from {currencyCode!r}. "
            "Use a three-letter ISO code such as USD, EUR, or GBP."
        )

    try:
        response = requests.get(
            _FRANKFURTER_LATEST,
            params={"from": code, "to": "ILS"},
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return "Could not reach the exchange-rate service. Try again later."

    rates = data.get("rates") if isinstance(data, dict) else None
    ils_rate = rates.get("ILS") if isinstance(rates, dict) else None
    if ils_rate is None:
        return f"{code} is not supported for conversion to ILS."

    as_of = data.get("date", "?")
    return f"1 {code} = {ils_rate:g} ILS (Frankfurter, as of {as_of})."


@function_tool
def get_weather(city: str) -> str:
    """Return current weather for a city using Open-Meteo."""
    name = (city or "").strip()
    if not name:
        return "No city was provided."

    try:
        geo = requests.get(
            _GEOCODE_URL,
            params={"name": name, "count": 1, "language": "he"},
            timeout=12,
        )
        geo.raise_for_status()
        gdata = geo.json()
    except requests.RequestException:
        return "Could not reach the geocoding service. Try again later."

    results = gdata.get("results") or []
    if not results:
        return f"Could not find a city named {name}."

    lat = results[0]["latitude"]
    lon = results[0]["longitude"]
    label = results[0].get("name") or name

    try:
        forecast = requests.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code",
                "timezone": "Asia/Jerusalem",
            },
            timeout=12,
        )
        forecast.raise_for_status()
        current = forecast.json().get("current") or {}
    except requests.RequestException:
        return "Could not reach the weather service. Try again later."

    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    if temp is None:
        return f"No current weather was returned for {label}."

    return f"{label}: {temp:g}°C, {_wmo_label(code)}."
