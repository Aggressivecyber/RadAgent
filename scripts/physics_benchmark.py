#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _round(value: float) -> float:
    return round(value, 6)


def _case_result(case: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    density = _safe_float(case.get("density_g_cm3"))
    mass_attenuation = _safe_float(case.get("mass_attenuation_cm2_g"))
    thickness = _safe_float(case.get("thickness_cm"))
    if density is None or mass_attenuation is None or thickness is None or thickness <= 0:
        return {
            "case_id": str(case.get("case_id") or ""),
            "status": "invalid",
            "passed": False,
            "error": "density_g_cm3, mass_attenuation_cm2_g, and positive thickness_cm are required",
        }

    reference_mu = density * mass_attenuation
    reference_transmission = math.exp(-reference_mu * thickness)
    reference = {
        "mass_attenuation_cm2_g": _round(mass_attenuation),
        "density_g_cm3": _round(density),
        "linear_attenuation_cm_inv": _round(reference_mu),
        "half_value_layer_cm": _round(math.log(2.0) / reference_mu) if reference_mu > 0 else 0.0,
        "transmission": _round(reference_transmission),
    }

    result: dict[str, Any] = {
        "case_id": str(case.get("case_id") or ""),
        "observable": str(case.get("observable") or "photon_transmission"),
        "material": str(case.get("material") or ""),
        "energy_MeV": _safe_float(case.get("energy_MeV")),
        "thickness_cm": _round(thickness),
        "reference": reference,
        "source": case.get("source"),
    }

    observed_transmission = _safe_float(case.get("observed_transmission"))
    if observed_transmission is None:
        result.update({"status": "reference_only", "observed": None, "passed": None})
        return result
    if observed_transmission <= 0 or observed_transmission >= 1:
        result.update(
            {
                "status": "invalid_observation",
                "observed": {"transmission": observed_transmission},
                "passed": False,
                "error": "observed_transmission must be between 0 and 1",
            }
        )
        return result

    observed_mu = -math.log(observed_transmission) / thickness
    relative_error = abs(observed_mu - reference_mu) / reference_mu if reference_mu else 0.0
    observed_cv = _safe_float(case.get("observed_cv"))
    max_relative_error = _safe_float(acceptance.get("max_relative_error"))
    max_cv = _safe_float(acceptance.get("max_cv"))
    error_ok = max_relative_error is None or relative_error <= max_relative_error
    cv_ok = observed_cv is None or max_cv is None or observed_cv <= max_cv

    result.update(
        {
            "status": "evaluated",
            "observed": {
                "transmission": _round(observed_transmission),
                "linear_attenuation_cm_inv": _round(observed_mu),
                "relative_error": _round(relative_error),
                "cv": _round(observed_cv) if observed_cv is not None else None,
            },
            "passed": bool(error_ok and cv_ok),
        }
    )
    return result


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    observed_cases = [case for case in cases if case.get("status") == "evaluated"]
    passed = [case for case in observed_cases if case.get("passed") is True]
    relative_errors = [
        float(_as_dict(case.get("observed")).get("relative_error"))
        for case in observed_cases
        if isinstance(_as_dict(case.get("observed")).get("relative_error"), int | float)
    ]
    return {
        "case_count": len(cases),
        "observed_case_count": len(observed_cases),
        "reference_only_count": sum(1 for case in cases if case.get("status") == "reference_only"),
        "pass_count": len(passed),
        "pass_rate": _round(len(passed) / len(observed_cases)) if observed_cases else 0.0,
        "median_relative_error": _round(median(relative_errors)) if relative_errors else None,
        "max_relative_error": _round(max(relative_errors)) if relative_errors else None,
    }


def _load_observations(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = _read_json(path)
    observations = _as_list(_as_dict(payload).get("observations")) if isinstance(payload, dict) else _as_list(payload)
    by_case: dict[str, dict[str, Any]] = {}
    for observation in observations:
        item = _as_dict(observation)
        case_id = str(item.get("case_id") or "")
        if case_id:
            by_case[case_id] = item
    return by_case


def collect_attenuation_benchmark(
    manifest: str | Path,
    *,
    observations: str | Path | None = None,
) -> dict[str, Any]:
    payload = _as_dict(_read_json(manifest))
    acceptance = _as_dict(payload.get("acceptance"))
    observation_by_case = _load_observations(observations)
    cases = []
    for raw_case in _as_list(payload.get("cases")):
        case = dict(_as_dict(raw_case))
        case_id = str(case.get("case_id") or "")
        if case_id in observation_by_case:
            case.update(observation_by_case[case_id])
        cases.append(_case_result(case, acceptance))
    return {
        "benchmark_id": str(payload.get("benchmark_id") or Path(manifest).stem),
        "description": str(payload.get("description") or ""),
        "sources": _as_list(payload.get("sources")),
        "acceptance": acceptance,
        "observations": str(observations) if observations else "",
        "aggregate": _aggregate(cases),
        "cases": cases,
    }


def to_markdown(summary: dict[str, Any]) -> str:
    aggregate = _as_dict(summary.get("aggregate"))
    lines = [
        f"# {summary.get('benchmark_id')}",
        "",
        str(summary.get("description") or ""),
        "",
        "## Aggregate",
        "",
        f"- Cases: {aggregate.get('case_count')}",
        f"- Observed cases: {aggregate.get('observed_case_count')}",
        f"- Reference-only cases: {aggregate.get('reference_only_count')}",
        f"- Pass count: {aggregate.get('pass_count')}",
        f"- Pass rate: {aggregate.get('pass_rate')}",
        f"- Median relative error: {aggregate.get('median_relative_error')}",
        f"- Max relative error: {aggregate.get('max_relative_error')}",
        "",
        "## Cases",
        "",
        "| Case | Material | Energy MeV | Thickness cm | T_ref | T_obs | Relative error | Status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in _as_list(summary.get("cases")):
        reference = _as_dict(case.get("reference"))
        observed = _as_dict(case.get("observed"))
        lines.append(
            "| {case_id} | {material} | {energy} | {thickness} | {t_ref} | {t_obs} | {err} | {status} |".format(
                case_id=case.get("case_id"),
                material=case.get("material"),
                energy=case.get("energy_MeV"),
                thickness=case.get("thickness_cm"),
                t_ref=reference.get("transmission"),
                t_obs=observed.get("transmission", ""),
                err=observed.get("relative_error", ""),
                status=case.get("status"),
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect RadAgent physics benchmark metrics.")
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON path.")
    parser.add_argument("--observations", default="", help="Optional observation overlay JSON path.")
    parser.add_argument("--output", default="", help="Optional output file.")
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format.",
    )
    args = parser.parse_args()

    summary = collect_attenuation_benchmark(
        args.manifest,
        observations=args.observations or None,
    )
    text = (
        json.dumps(summary, indent=2, ensure_ascii=False)
        if args.format == "json"
        else to_markdown(summary)
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
