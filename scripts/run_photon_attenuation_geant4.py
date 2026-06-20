#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _round(value: float) -> float:
    return round(value, 6)


def summarize_repeats(case_id: str, repeat_results: list[dict[str, Any]]) -> dict[str, Any]:
    transmissions: list[float] = []
    events_per_repeat: list[int] = []
    transmitted_per_repeat: list[int] = []
    for result in repeat_results:
        events = int(result.get("events") or 0)
        transmitted = int(result.get("transmitted") or 0)
        if events <= 0:
            continue
        events_per_repeat.append(events)
        transmitted_per_repeat.append(transmitted)
        transmissions.append(transmitted / events)

    observed_transmission = mean(transmissions) if transmissions else 0.0
    if len(transmissions) > 1 and observed_transmission > 0:
        observed_cv = stdev(transmissions) / observed_transmission
    elif transmissions and observed_transmission > 0:
        events = events_per_repeat[0]
        observed_cv = math.sqrt(observed_transmission * (1.0 - observed_transmission) / events)
        observed_cv /= observed_transmission
    else:
        observed_cv = 0.0

    return {
        "case_id": case_id,
        "observed_transmission": _round(observed_transmission),
        "observed_cv": _round(observed_cv),
        "repeat_count": len(transmissions),
        "events_per_repeat": events_per_repeat,
        "transmitted_per_repeat": transmitted_per_repeat,
        "raw_repeats": repeat_results,
    }


def load_json_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{") or not candidate.endswith("}"):
            continue
        return _as_dict(json.loads(candidate))
    raise ValueError("no JSON object found in Geant4 benchmark stdout")


def _geant4_env() -> dict[str, str]:
    env = dict(os.environ)
    prefix = env.get("GEANT4_INSTALL") or ""
    if prefix:
        env["CMAKE_PREFIX_PATH"] = (
            f"{prefix}:{env['CMAKE_PREFIX_PATH']}" if env.get("CMAKE_PREFIX_PATH") else prefix
        )
    return env


def build_executable(project_dir: str | Path, build_dir: str | Path) -> Path:
    project = Path(project_dir)
    build = Path(build_dir)
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cmake", "-S", str(project), "-B", str(build)],
        check=True,
        env=_geant4_env(),
    )
    subprocess.run(
        ["cmake", "--build", str(build), "--parallel", "2"],
        check=True,
        env=_geant4_env(),
    )
    return build / "photon_attenuation"


def _run_once(executable: Path, case: dict[str, Any], *, events: int, seed: int) -> dict[str, Any]:
    args = [
        str(executable),
        "--material",
        str(case["material"]),
        "--density",
        str(case["density_g_cm3"]),
        "--energy",
        str(case["energy_MeV"]),
        "--thickness",
        str(case["thickness_cm"]),
        "--events",
        str(events),
        "--seed",
        str(seed),
    ]
    completed = subprocess.run(args, check=True, text=True, capture_output=True)
    return load_json_from_stdout(completed.stdout)


def run_benchmark(
    manifest: str | Path,
    *,
    executable: str | Path,
    events: int,
    repeats: int,
    seed: int,
    case_limit: int = 0,
) -> dict[str, Any]:
    payload = _as_dict(_read_json(manifest))
    cases = _as_list(payload.get("cases"))
    if case_limit > 0:
        cases = cases[:case_limit]

    observations = []
    for case_index, raw_case in enumerate(cases):
        case = _as_dict(raw_case)
        repeat_results = []
        for repeat_index in range(repeats):
            repeat_seed = seed + case_index * 1000 + repeat_index
            repeat_results.append(
                _run_once(Path(executable), case, events=events, seed=repeat_seed)
            )
        observations.append(summarize_repeats(str(case.get("case_id") or ""), repeat_results))

    return {
        "benchmark_id": str(payload.get("benchmark_id") or Path(manifest).stem),
        "backend": "geant4",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest),
        "events": events,
        "repeats": repeats,
        "seed": seed,
        "case_count": len(observations),
        "observations": observations,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the Geant4 photon attenuation benchmark.")
    parser.add_argument("--manifest", default=str(root / "benchmarks" / "nist_photon_attenuation.json"))
    parser.add_argument(
        "--project-dir",
        default=str(root / "benchmarks" / "geant4_photon_attenuation"),
    )
    parser.add_argument(
        "--build-dir",
        default="/tmp/radagent_geant4_photon_attenuation_build",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--case-limit", type=int, default=0)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    executable = Path(args.build_dir) / "photon_attenuation"
    if not args.skip_build or not executable.exists():
        executable = build_executable(args.project_dir, args.build_dir)

    payload = run_benchmark(
        args.manifest,
        executable=executable,
        events=args.events,
        repeats=args.repeats,
        seed=args.seed,
        case_limit=args.case_limit,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
