from __future__ import annotations

import subprocess
from pathlib import Path


def test_reproduce_nist_benchmark_help_is_available() -> None:
    root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [str(root / "scripts" / "reproduce_nist_benchmark.sh"), "--help"],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "RadAgent NIST benchmark reproduction" in completed.stdout
    assert "--reference-only" in completed.stdout
    assert "--events" in completed.stdout


def test_setup_radagent_env_help_is_available() -> None:
    root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [str(root / "scripts" / "setup_radagent_env.sh"), "--help"],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "RadAgent environment setup" in completed.stdout
    assert "--venv" in completed.stdout
    assert "--skip-install" in completed.stdout


def test_reproduce_nist_reference_only_generates_reports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "reports"

    completed = subprocess.run(
        [
            str(root / "scripts" / "reproduce_nist_benchmark.sh"),
            "--reference-only",
            "--output-dir",
            str(output_dir),
        ],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "nist_photon_attenuation_reference_report.json").is_file()
    assert (output_dir / "nist_photon_attenuation_reference_report.md").is_file()
    assert "observed_case_count" in (
        output_dir / "nist_photon_attenuation_reference_report.json"
    ).read_text(encoding="utf-8")
