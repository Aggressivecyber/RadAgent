from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_runner_module() -> Any:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "run_photon_attenuation_geant4.py"
    spec = importlib.util.spec_from_file_location("run_photon_attenuation_geant4", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_repeats_computes_mean_transmission_and_repeat_cv() -> None:
    runner = _load_runner_module()

    summary = runner.summarize_repeats(
        "al-1mev-3cm",
        [
            {"events": 1000, "transmitted": 600},
            {"events": 1000, "transmitted": 620},
            {"events": 1000, "transmitted": 610},
        ],
    )

    assert summary["case_id"] == "al-1mev-3cm"
    assert summary["observed_transmission"] == 0.61
    assert summary["observed_cv"] == 0.016393
    assert summary["repeat_count"] == 3
    assert summary["events_per_repeat"] == [1000, 1000, 1000]
    assert summary["transmitted_per_repeat"] == [600, 620, 610]


def test_summarize_repeats_uses_binomial_cv_for_single_repeat() -> None:
    runner = _load_runner_module()

    summary = runner.summarize_repeats(
        "pb-0p5mev-2cm",
        [{"events": 100000, "transmitted": 2600}],
    )

    assert summary["observed_transmission"] == 0.026
    assert summary["observed_cv"] == 0.019355


def test_load_json_from_stdout_ignores_geant4_banner() -> None:
    runner = _load_runner_module()

    payload = runner.load_json_from_stdout(
        """
        Geant4 version Name: geant4-11-03
        ### Run 0 starts.
        {"events":1000,"transmitted":402,"transmission":0.402}
        """
    )

    assert payload == {"events": 1000, "transmitted": 402, "transmission": 0.402}
