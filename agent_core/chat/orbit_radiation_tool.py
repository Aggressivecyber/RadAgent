"""Read-only orbit-radiation query helper for Copilot chat turns."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Literal

from knowledge_base.space_radiation.ap8ae8 import AP8AE8_DATASET_ID

from agent_core.space_radiation.ap8ae8_provider import (
    OrbitRadiationRequest,
    SpaceRadiationProvider,
    is_orbit_radiation_request,
)

SolarPeriod = Literal["min", "max"]
FluxMode = Literal["integral", "differential"]


def query_orbit_radiation(message: str) -> dict[str, Any] | None:
    """Return local AP8/AE8 query diagnostics for an orbit-radiation question.

    The chat tool is intentionally read-only: it validates what Copilot already
    knows, selects the AP8/AE8 model when possible, and reports missing inputs.
    Spectrum generation still happens later in task planning after human approval.
    """
    if not is_orbit_radiation_request(message):
        return None

    request = _request_from_message(message)
    provider = SpaceRadiationProvider()
    validation = provider.validate_request(request)
    errors: list[str] = []
    model_name = ""
    if request.particle and request.solar_period:
        try:
            model_name = provider.select_model(request)
        except ValueError as exc:
            errors.append(str(exc))

    missing_fields = list(validation.missing_fields)
    if errors and "particle" not in missing_fields:
        missing_fields.append("particle")
    ready = validation.ready and not errors

    return {
        "tool": "orbit_radiation.ap8ae8.query",
        "provider": "ap8ae8",
        "dataset_id": AP8AE8_DATASET_ID,
        "ready": ready,
        "model": model_name,
        "request": _compact_request(request),
        "missing_fields": missing_fields,
        "notes": validation.notes + errors,
        "next_questions": _next_questions(missing_fields),
        "limitations": [
            "AP8/AE8 is a static trapped proton/electron belt model.",
            "Altitude/inclination alone are not enough for this adapter.",
            "Use TLE, geodetic samples, or L-shell with B/B0 for source generation.",
        ],
    }


def _request_from_message(message: str) -> OrbitRadiationRequest:
    return OrbitRadiationRequest(
        particle=_extract_particle(message),
        solar_period=_extract_solar_period(message),
        l_shell=_extract_l_shell(message),
        bb0=_extract_bb0(message),
        altitude_km=_extract_altitude_km(message),
        inclination_deg=_extract_inclination_deg(message),
        flux_mode=_extract_flux_mode(message),
        events=_extract_events(message) or 1000,
    )


def _extract_particle(message: str) -> str | None:
    text = message.lower()
    if re.search(r"\bprotons?\b|\bp\+\b|质子|ap[- ]?8", text, re.IGNORECASE):
        return "proton"
    if re.search(r"\belectrons?\b|\be-\b|电子|ae[- ]?8", text, re.IGNORECASE):
        return "electron"
    return None


def _extract_solar_period(message: str) -> SolarPeriod | None:
    text = message.lower()
    if re.search(r"solar\s*min|minimum|太阳.*(极小|低|最小)|低太阳", text):
        return "min"
    if re.search(r"solar\s*max|maximum|太阳.*(极大|高|最大)|高太阳", text):
        return "max"
    if re.search(r"\bmin\b", text):
        return "min"
    if re.search(r"\bmax\b", text):
        return "max"
    return None


def _extract_l_shell(message: str) -> float | None:
    patterns = (
        r"(?:L[-\s]?shell|L壳|L)\s*[=:：]\s*([0-9]+(?:\.[0-9]+)?)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:L[-\s]?shell|L壳)",
    )
    return _first_float(message, patterns)


def _extract_bb0(message: str) -> float | None:
    patterns = (
        r"(?:B\s*/\s*B0|B/B0|BB0|B0比|磁场比)\s*[=:：]\s*([0-9]+(?:\.[0-9]+)?)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:B\s*/\s*B0|B/B0|BB0|B0比|磁场比)",
    )
    return _first_float(message, patterns)


def _extract_altitude_km(message: str) -> float | None:
    patterns = (
        r"(?:altitude|高度|轨道高度)\s*[=:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*km",
        r"([0-9]+(?:\.[0-9]+)?)\s*km",
    )
    return _first_float(message, patterns)


def _extract_inclination_deg(message: str) -> float | None:
    patterns = (
        r"(?:inclination|倾角)\s*[=:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:deg|度)?",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:deg|度)\s*(?:inclination|倾角)",
    )
    return _first_float(message, patterns)


def _extract_flux_mode(message: str) -> FluxMode:
    text = message.lower()
    if re.search(r"\bintegral\b|积分|累积", text):
        return "integral"
    return "differential"


def _extract_events(message: str) -> int | None:
    match = re.search(
        r"([0-9]+)\s*(?:events|particles|histories|事件|粒子)",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    return max(int(match.group(1)), 1)


def _first_float(message: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _compact_request(request: OrbitRadiationRequest) -> dict[str, Any]:
    payload = asdict(request)
    return {key: value for key, value in payload.items() if value not in (None, [], ())}


def _next_questions(missing_fields: list[str]) -> list[str]:
    questions: list[str] = []
    if "particle" in missing_fields:
        questions.append("确认 trapped belt 粒子类型：proton/AP8 还是 electron/AE8？")
    if "solar_period" in missing_fields:
        questions.append("确认太阳活动期：solar min 还是 solar max？")
    if "l_shell" in missing_fields or "bb0" in missing_fields:
        questions.append("提供 TLE、geodetic samples，或直接给 L-shell 与 B/B0。")
    return questions
