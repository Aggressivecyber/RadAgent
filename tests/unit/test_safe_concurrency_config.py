from __future__ import annotations

from unittest.mock import patch

from agent_core.config.environment import load_environment, resolve_safe_concurrency


def test_resolve_safe_concurrency_respects_explicit_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_G4_MODULE_MAX_CONCURRENCY", "2")

    assert (
        resolve_safe_concurrency(
            4,
            override_env="RADAGENT_G4_MODULE_MAX_CONCURRENCY",
            hard_cap=4,
            memory_per_worker_gb=2.0,
        )
        == 2
    )


def test_resolve_safe_concurrency_clamps_override_to_workload(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_G4_MODULE_MAX_CONCURRENCY", "99")

    assert (
        resolve_safe_concurrency(
            3,
            override_env="RADAGENT_G4_MODULE_MAX_CONCURRENCY",
            hard_cap=4,
            memory_per_worker_gb=2.0,
        )
        == 3
    )


def test_resolve_safe_concurrency_uses_cpu_memory_and_hard_cap(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RADAGENT_G4_MODULE_MAX_CONCURRENCY", raising=False)
    with (
        patch("agent_core.config.environment.os.cpu_count", return_value=16),
        patch("agent_core.config.environment._total_memory_gb", return_value=6.0),
    ):
        assert (
            resolve_safe_concurrency(
                10,
                override_env="RADAGENT_G4_MODULE_MAX_CONCURRENCY",
                hard_cap=4,
                memory_per_worker_gb=2.0,
            )
            == 3
        )


def test_load_environment_exposes_safe_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_G4_MODULE_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("RADAGENT_SCENARIO_MAX_CONCURRENCY", "2")

    env = load_environment()

    assert env.concurrency.g4_module_max_concurrency == 1
    assert env.concurrency.scenario_max_concurrency == 2
    assert env.concurrency.cpu_count >= 1
