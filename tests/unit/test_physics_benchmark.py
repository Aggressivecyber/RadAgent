from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_benchmark_module() -> Any:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "physics_benchmark.py"
    spec = importlib.util.spec_from_file_location("physics_benchmark", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_attenuation_benchmark_computes_reference_and_observed_error(
    tmp_path: Path,
) -> None:
    benchmark = _load_benchmark_module()
    manifest = tmp_path / "nist_photon.json"
    manifest.write_text(
        json.dumps(
            {
                "benchmark_id": "nist-photon-attenuation-smoke",
                "description": "Minimal NIST photon attenuation benchmark.",
                "acceptance": {"max_relative_error": 0.05, "max_cv": 0.02},
                "cases": [
                    {
                        "case_id": "pb-1mev-1cm",
                        "observable": "photon_transmission",
                        "material": "Pb",
                        "energy_MeV": 1.0,
                        "density_g_cm3": 11.34,
                        "mass_attenuation_cm2_g": 0.07102,
                        "thickness_cm": 1.0,
                        "observed_transmission": 0.45,
                        "observed_cv": 0.01,
                    },
                    {
                        "case_id": "al-1mev-3cm",
                        "observable": "photon_transmission",
                        "material": "Al",
                        "energy_MeV": 1.0,
                        "density_g_cm3": 2.699,
                        "mass_attenuation_cm2_g": 0.06146,
                        "thickness_cm": 3.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = benchmark.collect_attenuation_benchmark(manifest)

    assert summary["benchmark_id"] == "nist-photon-attenuation-smoke"
    assert summary["aggregate"]["case_count"] == 2
    assert summary["aggregate"]["observed_case_count"] == 1
    assert summary["aggregate"]["pass_count"] == 1
    assert summary["aggregate"]["pass_rate"] == 1.0

    observed = summary["cases"][0]
    assert observed["case_id"] == "pb-1mev-1cm"
    assert observed["reference"]["linear_attenuation_cm_inv"] == 0.805367
    assert observed["reference"]["transmission"] == 0.446924
    assert observed["observed"]["linear_attenuation_cm_inv"] == 0.798508
    assert observed["observed"]["relative_error"] == 0.008517
    assert observed["passed"] is True

    pending = summary["cases"][1]
    assert pending["case_id"] == "al-1mev-3cm"
    assert pending["status"] == "reference_only"
    assert pending["passed"] is None


def test_collect_attenuation_benchmark_fails_observed_case_outside_threshold(
    tmp_path: Path,
) -> None:
    benchmark = _load_benchmark_module()
    manifest = tmp_path / "nist_photon.json"
    manifest.write_text(
        json.dumps(
            {
                "acceptance": {"max_relative_error": 0.05, "max_cv": 0.02},
                "cases": [
                    {
                        "case_id": "water-1mev-10cm",
                        "observable": "photon_transmission",
                        "material": "Water",
                        "energy_MeV": 1.0,
                        "density_g_cm3": 1.0,
                        "mass_attenuation_cm2_g": 0.07072,
                        "thickness_cm": 10.0,
                        "observed_transmission": 0.60,
                        "observed_cv": 0.01,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = benchmark.collect_attenuation_benchmark(manifest)

    assert summary["aggregate"]["observed_case_count"] == 1
    assert summary["aggregate"]["pass_count"] == 0
    assert summary["aggregate"]["pass_rate"] == 0.0
    assert summary["aggregate"]["max_relative_error"] == 0.277679
    assert summary["cases"][0]["passed"] is False


def test_repository_nist_photon_manifest_is_runnable_reference_set() -> None:
    benchmark = _load_benchmark_module()
    root = Path(__file__).resolve().parents[2]
    manifest = root / "benchmarks" / "nist_photon_attenuation.json"

    summary = benchmark.collect_attenuation_benchmark(manifest)

    assert summary["benchmark_id"] == "nist-photon-attenuation-v1"
    assert len(summary["sources"]) >= 3
    assert summary["aggregate"]["case_count"] == 18
    assert summary["aggregate"]["reference_only_count"] == 18
    assert summary["aggregate"]["observed_case_count"] == 0
    assert summary["cases"][0]["reference"]["transmission"] == 0.400461


def test_collect_attenuation_benchmark_applies_observation_overlay(tmp_path: Path) -> None:
    benchmark = _load_benchmark_module()
    manifest = tmp_path / "nist_photon.json"
    observations = tmp_path / "observations.json"
    manifest.write_text(
        json.dumps(
            {
                "acceptance": {"max_relative_error": 0.05, "max_cv": 0.02},
                "cases": [
                    {
                        "case_id": "al-1mev-3cm",
                        "observable": "photon_transmission",
                        "material": "Al",
                        "energy_MeV": 1.0,
                        "density_g_cm3": 2.699,
                        "mass_attenuation_cm2_g": 0.06146,
                        "thickness_cm": 3.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    observations.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "case_id": "al-1mev-3cm",
                        "observed_transmission": 0.61,
                        "observed_cv": 0.01,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = benchmark.collect_attenuation_benchmark(manifest, observations=observations)

    assert summary["aggregate"]["observed_case_count"] == 1
    assert summary["cases"][0]["status"] == "evaluated"
    assert summary["cases"][0]["observed"]["transmission"] == 0.61
