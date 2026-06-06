#!/usr/bin/env python3
"""Collect lightweight artifacts from a completed RadAgent job directory.

Copies summaries, metadata, and CSV headers (5 rows max) — never large
binary files.

Usage:
    python scripts/collect_mvp1_artifacts.py \
        --job-dir simulation_workspace/jobs/job_xxx \
        --output-dir review_artifacts/mvp1_e2e/latest/output
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 100 * 1024  # 100 KB
_BLOCKED_EXTENSIONS = {".hdf5", ".h5", ".root", ".raw", ".bin"}
_CSV_HEAD_ROWS = 5

# Files to collect from each job stage
_COLLECTION_SPEC: list[tuple[str, str, bool]] = [
    # (source_rel_path, dest_filename, truncate_content)
    ("00_request/user_query.md", "user_query.md", False),
    ("02_task_spec/task_spec.json", "task_spec.json", False),
    ("03_simulation_ir/simulation_ir.json", "simulation_ir.json", False),
    ("04_generated_code/proposed_patch.json", "proposed_patch_summary.json", True),
    ("09_validation/gate_results.json", "gate_results.json", False),
    ("10_report/final_report.md", "final_report.md", False),
]

# Output files to collect (head only for CSV)
_G4_OUTPUT_FILES: list[tuple[str, bool]] = [
    ("g4_summary.json", False),
    ("provenance.json", False),
    ("edep_3d.csv", True),
    ("dose_3d.csv", True),
    ("event_table.csv", True),
]


def _sha256(data: bytes) -> str:
    """Compute SHA256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _truncate_patch_content(patch_json: dict, max_chars: int = 200) -> dict:
    """Truncate new_content fields in proposed_patch.json."""
    changed = patch_json.get("changed_files", [])
    for entry in changed:
        if "new_content" in entry and len(entry["new_content"]) > max_chars:
            entry["new_content"] = entry["new_content"][:max_chars] + "\n... [truncated]"
    return patch_json


def _csv_head(src: Path, dest: Path) -> bool:
    """Copy CSV header + first N data rows."""
    try:
        with src.open(newline="") as f:
            reader = csv.reader(f)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= _CSV_HEAD_ROWS:
                    break
        with dest.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return True
    except Exception as exc:
        logger.warning("Failed to read CSV %s: %s", src, exc)
        return False


def collect(job_dir: Path, output_dir: Path) -> dict:
    """Collect lightweight artifacts from job_dir into output_dir.

    Returns a manifest dict listing collected files and their sizes.
    """
    if not job_dir.is_dir():
        logger.error("Job directory does not exist: %s", job_dir)
        return {"error": "job_dir_not_found", "files": []}

    output_dir.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    manifest_files: list[dict] = []

    def _save(name: str, data: bytes) -> None:
        dest = output_dir / name
        dest.write_bytes(data)
        checksums[name] = _sha256(data)
        manifest_files.append(
            {"name": name, "size": len(data), "checksum": checksums[name]}
        )

    # Collect stage artifacts
    for src_rel, dest_name, truncate in _COLLECTION_SPEC:
        src = job_dir / src_rel
        if not src.is_file():
            logger.info("Skipping missing file: %s", src_rel)
            continue
        if src.stat().st_size > _MAX_FILE_SIZE:
            logger.warning(
                "Skipping large file (%d KB): %s",
                src.stat().st_size // 1024,
                src_rel,
            )
            continue
        if src.suffix.lower() in _BLOCKED_EXTENSIONS:
            logger.warning("Skipping blocked extension: %s", src_rel)
            continue

        if truncate and src.suffix == ".json":
            try:
                data = json.loads(src.read_text())
                data = _truncate_patch_content(data)
                _save(dest_name, json.dumps(data, indent=2, ensure_ascii=False).encode())
            except Exception as exc:
                logger.warning("Failed to truncate JSON %s: %s", src_rel, exc)
                _save(dest_name, src.read_bytes())
        else:
            _save(dest_name, src.read_bytes())

    # Collect Geant4 output files
    g4_output = job_dir / "08_data_packages" / "g4_output_package"
    for fname, head_only in _G4_OUTPUT_FILES:
        src = g4_output / fname
        if not src.is_file():
            logger.info("Skipping missing G4 output: %s", fname)
            continue
        if src.stat().st_size > _MAX_FILE_SIZE:
            logger.warning(
                "Skipping large G4 output (%d KB): %s",
                src.stat().st_size // 1024,
                fname,
            )
            continue

        if head_only and src.suffix == ".csv":
            dest_name = fname.replace(".csv", "_head.csv")
            if _csv_head(src, output_dir / dest_name):
                data = (output_dir / dest_name).read_bytes()
                checksums[dest_name] = _sha256(data)
                manifest_files.append(
                    {"name": dest_name, "size": len(data), "checksum": checksums[dest_name]}
                )
        else:
            _save(fname, src.read_bytes())

    # Write checksums
    checksum_file = output_dir / "checksums.json"
    checksum_file.write_text(json.dumps(checksums, indent=2))

    # Write manifest
    manifest = {
        "job_dir": str(job_dir),
        "collected_at": __import__("datetime").datetime.now().isoformat(),
        "file_count": len(manifest_files),
        "files": manifest_files,
    }
    manifest_file = output_dir / "collection_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    logger.info("Collected %d files to %s", len(manifest_files), output_dir)
    return manifest


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Collect lightweight artifacts from a job directory"
    )
    parser.add_argument("--job-dir", type=Path, required=True, help="Path to job directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("review_artifacts/mvp1_e2e/latest/output"),
        help="Output directory for collected artifacts",
    )
    args = parser.parse_args()

    manifest = collect(args.job_dir.resolve(), args.output_dir.resolve())
    if manifest.get("error"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
