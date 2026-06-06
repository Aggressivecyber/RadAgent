#!/usr/bin/env python3
"""Package collected artifacts into a review-ready bundle.

Reads e2e_results.json and collected artifacts to produce review_report.json.

Usage:
    python scripts/make_review_artifact.py --mode dev \
        --run-results review_artifacts/mvp1_e2e/latest/e2e_results.json \
        --artifacts-dir review_artifacts/mvp1_e2e/latest/output \
        --output-dir review_artifacts/mvp1_e2e/latest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def _extract_mvp1_status(report_path: Path) -> str:
    """Extract MVP-1 verification status from final_report.md."""
    if not report_path.is_file():
        return "UNKNOWN"
    text = report_path.read_text(errors="replace")
    if "**MVP-1: PASSED**" in text:
        return "MVP-1 VERIFIED"
    if "**MVP-1: FAILED**" in text:
        return "MVP-1 FAILED"
    if "**MVP-1: NOT VERIFIED**" in text:
        return "NOT VERIFIED"
    return "UNKNOWN"


def _extract_gate_summary(artifacts_dir: Path) -> dict:
    """Extract gate summary from gate_results.json."""
    gate_file = artifacts_dir / "gate_results.json"
    if not gate_file.is_file():
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "skipped_ids": []}

    try:
        gates = json.loads(gate_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "skipped_ids": []}

    passed = sum(1 for g in gates if g.get("severity") in ("pass", "warning"))
    failed = sum(1 for g in gates if g.get("severity") in ("fail", "block"))
    skipped_gates = [g for g in gates if g.get("severity") == "skipped"]
    skipped_ids = [g.get("gate_id") for g in skipped_gates]

    return {
        "total": len(gates),
        "passed": passed,
        "failed": failed,
        "skipped": len(skipped_gates),
        "skipped_ids": sorted(sid for sid in skipped_ids if sid is not None),
    }


def _collect_file_list(artifacts_dir: Path) -> tuple[list[str], int]:
    """List all files in artifacts_dir and compute total size."""
    files = []
    total_size = 0
    if artifacts_dir.is_dir():
        for p in sorted(artifacts_dir.rglob("*")):
            if p.is_file():
                files.append(p.name)
                total_size += p.stat().st_size
    return files, total_size


def make_review_artifact(
    mode: str,
    run_results_path: Path,
    artifacts_dir: Path,
    output_dir: Path,
) -> dict:
    """Produce review_report.json from run results and collected artifacts."""
    mode_str = "mvp1_acceptance" if mode == "acceptance" else "dev_no_geant4_env"

    # Read run results
    run_results: dict = {}
    if run_results_path.is_file():
        try:
            run_results = json.loads(run_results_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            run_results = {"error": str(exc)}

    # Extract status from report
    verification_status = _extract_mvp1_status(artifacts_dir / "final_report.md")

    # Extract gate summary
    gate_summary = _extract_gate_summary(artifacts_dir)

    # Collect file list
    files, total_size = _collect_file_list(artifacts_dir)

    review_report = {
        "mvp1_review": {
            "mode": mode_str,
            "scenario": run_results.get("scenario", "unknown"),
            "verification_status": verification_status,
            "timestamp": datetime.now(UTC).isoformat(),
            "duration_seconds": run_results.get("duration_seconds", 0),
        },
        "test_results": run_results.get("results", {}),
        "gate_summary": gate_summary,
        "artifacts": {
            "files": files,
            "total_size_bytes": total_size,
        },
    }

    # Write review report
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / "review_report.json"
    report_file.write_text(json.dumps(review_report, indent=2))

    # Write artifact manifest with checksums
    manifest: dict = {"files": []}
    if artifacts_dir.is_dir():
        for p in sorted(artifacts_dir.rglob("*")):
            if p.is_file():
                manifest["files"].append({
                    "name": p.name,
                    "size": p.stat().st_size,
                    "checksum": hashlib.sha256(p.read_bytes()).hexdigest(),
                })
    manifest_file = output_dir / "review_artifact_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    return review_report


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Package review artifacts")
    parser.add_argument("--mode", choices=["dev", "acceptance"], required=True)
    parser.add_argument(
        "--run-results", type=Path, required=True, help="Path to e2e_results.json"
    )
    parser.add_argument(
        "--artifacts-dir", type=Path, required=True, help="Path to collected artifacts dir"
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    report = make_review_artifact(
        args.mode,
        args.run_results.resolve(),
        args.artifacts_dir.resolve(),
        args.output_dir.resolve(),
    )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
