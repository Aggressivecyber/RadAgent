from __future__ import annotations

from pathlib import Path

from agent_core.config.environment import (
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_MODEL_LITE,
    DEFAULT_MODEL_MAX,
    DEFAULT_MODEL_PRO,
    load_environment,
    model_endpoint_requires_api_key,
    validate_acceptance_environment,
    write_project_env_values,
)
from agent_core.models.schemas import ModelTier
from agent_core.tools.geant4_runner import Geant4Runner


def test_load_environment_reads_models_and_software(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://models.example/v1",
                "RADAGENT_PRO_API_KEY_ENV=TEST_RADAGENT_KEY",
                "TEST_RADAGENT_KEY=test-key",
                "RADAGENT_MODEL_PRO=test-pro-model",
                "GEANT4_INSTALL_DIR=/opt/geant4",
                "GEANT4_CONFIG_BIN=/opt/geant4/bin/geant4-config",
                "GEANT4_SETUP_SCRIPT=/opt/geant4/bin/geant4.sh",
                "TCAD_INSTALL_DIR=/opt/synopsys/tcad",
                "TCAD_SDE_BIN=/opt/synopsys/tcad/bin/sde",
            ]
        )
    )

    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    monkeypatch.delenv("RADAGENT_PRO_API_KEY_ENV", raising=False)
    monkeypatch.delenv("GEANT4_INSTALL_DIR", raising=False)
    monkeypatch.delenv("GEANT4_CONFIG_BIN", raising=False)
    monkeypatch.delenv("GEANT4_SETUP_SCRIPT", raising=False)
    monkeypatch.delenv("TCAD_INSTALL_DIR", raising=False)
    monkeypatch.delenv("TCAD_SDE_BIN", raising=False)
    env = load_environment(env_file)

    assert env.models[ModelTier.PRO].base_url == "https://models.example/v1"
    assert env.models[ModelTier.PRO].model_name == "test-pro-model"
    assert env.models[ModelTier.PRO].api_key_env == "TEST_RADAGENT_KEY"
    assert env.models[ModelTier.PRO].api_key_configured is True
    assert env.software.geant4_install_dir == "/opt/geant4"
    assert env.software.geant4_config_bin == "/opt/geant4/bin/geant4-config"
    assert env.software.tcad_install_dir == "/opt/synopsys/tcad"
    assert env.software.tcad_sde_bin == "/opt/synopsys/tcad/bin/sde"


def test_geant4_runner_uses_environment_paths(monkeypatch) -> None:
    monkeypatch.setenv("GEANT4_INSTALL_DIR", "/tmp/custom-geant4")
    monkeypatch.setenv("GEANT4_CONFIG_BIN", "/tmp/custom-geant4/bin/geant4-config")
    monkeypatch.setenv("GEANT4_SETUP_SCRIPT", "/tmp/custom-geant4/bin/geant4.sh")

    runner = Geant4Runner()

    assert runner.geant4_dir == "/tmp/custom-geant4"
    assert runner.geant4_config_bin == "/tmp/custom-geant4/bin/geant4-config"
    assert runner.geant4_setup_script == "/tmp/custom-geant4/bin/geant4.sh"


def test_token_plan_model_endpoint_requires_access_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1",
                "RADAGENT_MODEL_PRO=mimo-v2.5-pro",
                "RADAGENT_PRO_API_KEY_ENV=RADAGENT_API_KEY",
            ]
        )
    )
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    monkeypatch.delenv("RADAGENT_PRO_API_KEY_ENV", raising=False)

    env = load_environment(env_file)

    assert model_endpoint_requires_api_key(env.models[ModelTier.PRO].base_url) is True
    assert env.models[ModelTier.PRO].api_key_configured is False


def test_default_model_config_is_token_plan_mimo(monkeypatch) -> None:
    for key in (
        "RADAGENT_MODEL_BASE_URL",
        "RADAGENT_LITE_BASE_URL",
        "RADAGENT_PRO_BASE_URL",
        "RADAGENT_MAX_BASE_URL",
        "RADAGENT_MODEL_LITE",
        "RADAGENT_MODEL_PRO",
        "RADAGENT_MODEL_MAX",
    ):
        monkeypatch.delenv(key, raising=False)

    env = load_environment()

    assert env.models[ModelTier.LITE].base_url == DEFAULT_MODEL_BASE_URL
    assert env.models[ModelTier.PRO].base_url == DEFAULT_MODEL_BASE_URL
    assert env.models[ModelTier.MAX].base_url == DEFAULT_MODEL_BASE_URL
    assert env.models[ModelTier.LITE].model_name == DEFAULT_MODEL_LITE
    assert env.models[ModelTier.PRO].model_name == DEFAULT_MODEL_PRO
    assert env.models[ModelTier.MAX].model_name == DEFAULT_MODEL_MAX
    assert env.models[ModelTier.LITE].context_window_tokens == 1_000_000
    assert env.models[ModelTier.PRO].context_window_tokens == 1_000_000
    assert env.models[ModelTier.MAX].context_window_tokens == 1_000_000


def test_regular_model_endpoint_requires_local_api_key() -> None:
    assert model_endpoint_requires_api_key("https://models.example/v1") is True


def test_token_plan_model_endpoint_uses_env_key_like_regular_api(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "RADAGENT_MODEL_BASE_URL",
        "https://token-plan-cn.xiaomimimo.com/v1",
    )
    monkeypatch.setenv("RADAGENT_LITE_API_KEY_ENV", "RADAGENT_API_KEY")
    monkeypatch.setenv("RADAGENT_PRO_API_KEY_ENV", "RADAGENT_API_KEY")
    monkeypatch.setenv("RADAGENT_MAX_API_KEY_ENV", "RADAGENT_API_KEY")
    monkeypatch.setenv("RADAGENT_API_KEY", "plain-env-key")

    ok, errors = validate_acceptance_environment(
        require_model=True,
        require_geant4=False,
    )

    assert ok is True
    assert errors == []


def test_max_tier_reads_frontend_max_tokens_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://models.example/v1",
                "RADAGENT_MAX_MAX_TOKENS=32000",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_MAX_MAX_TOKENS", raising=False)

    env = load_environment(env_file)

    assert env.models[ModelTier.MAX].max_tokens == 32000


def test_max_tier_reads_context_window_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://models.example/v1",
                "RADAGENT_MAX_CONTEXT_WINDOW_TOKENS=200000",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_MAX_CONTEXT_WINDOW_TOKENS", raising=False)

    env = load_environment(env_file)

    assert env.models[ModelTier.MAX].context_window_tokens == 200000


def test_default_model_timeouts_only_guard_dead_connections(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for key in (
        "RADAGENT_LITE_TIMEOUT_S",
        "RADAGENT_PRO_TIMEOUT_S",
        "RADAGENT_MAX_TIMEOUT_S",
    ):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    env = load_environment(env_file)

    assert env.models[ModelTier.LITE].timeout_s == 30.0
    assert env.models[ModelTier.PRO].timeout_s == 360.0
    assert env.models[ModelTier.MAX].timeout_s == 420.0


def test_write_project_env_values_upserts_without_exposing_other_lines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# keep comment\nRADAGENT_MODEL_BASE_URL=https://old.example/v1\nOTHER=value\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)

    write_project_env_values(
        {
            "RADAGENT_MODEL_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
            "RADAGENT_MODEL_PRO": "mimo-v2.5-pro",
        },
        env_path=env_file,
    )

    text = env_file.read_text(encoding="utf-8")
    assert "# keep comment" in text
    assert "OTHER=value" in text
    assert "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1" in text
    assert "RADAGENT_MODEL_PRO=mimo-v2.5-pro" in text
    assert (
        load_environment(env_file).models[ModelTier.PRO].base_url
        == "https://token-plan-cn.xiaomimimo.com/v1"
    )


def test_validate_acceptance_environment_reports_missing_tcad(monkeypatch) -> None:
    monkeypatch.delenv("TCAD_INSTALL_DIR", raising=False)
    monkeypatch.delenv("STROOT", raising=False)
    monkeypatch.delenv("TCAD_SDE_BIN", raising=False)
    monkeypatch.delenv("TCAD_SVISUAL_BIN", raising=False)
    monkeypatch.delenv("TCAD_SWB_BIN", raising=False)

    ok, errors = validate_acceptance_environment(
        require_model=False,
        require_geant4=False,
        require_tcad=True,
    )

    assert ok is False
    assert any("TCAD" in error for error in errors)
