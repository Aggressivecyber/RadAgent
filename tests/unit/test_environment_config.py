from __future__ import annotations

from pathlib import Path

from agent_core.config.environment import load_environment, validate_acceptance_environment
from agent_core.models.schemas import ModelTier
from agent_core.tools.geant4_runner import Geant4Runner


def test_load_environment_reads_models_and_software(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_PROVIDER=openai_compatible",
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
