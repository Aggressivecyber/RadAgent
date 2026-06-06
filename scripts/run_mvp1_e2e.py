#!/usr/bin/env python3
"""Run MVP-1 E2E tests and produce a results JSON.

Usage:
    python scripts/run_mvp1_e2e.py --mode dev
    python scripts/run_mvp1_e2e.py --mode acceptance
    python scripts/run_mvp1_e2e.py --mode both --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_E2E_QUERY = "10 MeV proton vertical incidence on 300um Si"


def _run_pytest(
    test_file: str, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run pytest and capture output."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(_PROJECT_ROOT / test_file),
        "-v", "--tb=short", "-m", "e2e",
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def _parse_pytest_output(output: str) -> dict[str, int]:
    """Parse pytest output for pass/fail/error/skip counts."""
    results = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    # Match lines like "tests/e2e/test.py::test_name PASSED"
    results["passed"] = len(re.findall(r"\bPASSED\b", output))
    results["failed"] = len(re.findall(r"\bFAILED\b", output))
    results["errors"] = len(re.findall(r"\bERROR\b", output))
    results["skipped"] = len(re.findall(r"\bSKIPPED\b", output))

    return results


def _write_results(
    mode: str,
    results: dict[str, int],
    duration: float,
    exit_code: int,
    output: str,
    output_dir: Path,
    as_json: bool,
) -> None:
    """Write results JSON and optionally print summary."""
    mode_str = "mvp1_acceptance" if mode == "acceptance" else "dev_no_geant4_env"
    result_data = {
        "mode": mode_str,
        "timestamp": datetime.now(UTC).isoformat(),
        "scenario": _E2E_QUERY,
        "results": results,
        "duration_seconds": round(duration, 2),
        "pytest_exit_code": exit_code,
        "pytest_output": output[-10000:] if len(output) > 10000 else output,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = output_dir / "e2e_results.json"
    results_file.write_text(json.dumps(result_data, indent=2))

    if as_json:
        print(json.dumps(result_data, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"MVP-1 E2E ({mode_str})")
        print(f"  Passed:  {results['passed']}")
        print(f"  Failed:  {results['failed']}")
        print(f"  Errors:  {results['errors']}")
        print(f"  Skipped: {results['skipped']}")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Results: {results_file}")
        print(f"{'='*60}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run MVP-1 E2E tests")
    parser.add_argument(
        "--mode",
        choices=["dev", "acceptance", "both"],
        default="dev",
        help="Test mode (default: dev)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_PROJECT_ROOT / "review_artifacts" / "mvp1_e2e" / "latest",
        help="Output directory for results",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    overall_exit = 0

    modes = ["dev", "acceptance"] if args.mode == "both" else [args.mode]
    test_files = {
        "dev": "tests/e2e/test_mvp1_e2e_dev.py",
        "acceptance": "tests/e2e/test_mvp1_e2e_acceptance.py",
    }

    for mode in modes:
        test_file = test_files[mode]
        print(f"\nRunning MVP-1 E2E ({mode} mode)...")
        start = time.time()
        try:
            proc = _run_pytest(test_file)
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT: {mode} mode E2E exceeded 600s")
            overall_exit = 1
            continue

        duration = time.time() - start
        results = _parse_pytest_output(proc.stdout + proc.stderr)
        _write_results(
            mode, results, duration, proc.returncode,
            proc.stdout, args.output_dir, args.json,
        )

        if proc.returncode != 0:
            overall_exit = 1

    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
