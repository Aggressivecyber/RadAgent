"""Central RadAgent environment configuration.

This module is the single read surface for model endpoints, model names,
API-key env var names, RAG endpoints, and local simulation tool locations.
It intentionally reports whether secrets are configured without exposing
secret values.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from agent_core.models.schemas import ModelProvider, ModelTier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env(env_path: Path | None = None) -> None:
    """Load project .env values without overriding exported shell values."""
    load_dotenv(env_path or DEFAULT_ENV_PATH, override=False)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _path_env(name: str, default: str = "") -> str:
    value = _env(name, default)
    if value:
        return str(Path(value).expanduser())
    return ""


@dataclass(frozen=True)
class ModelTierEnvironment:
    tier: ModelTier
    provider: ModelProvider
    model_name: str
    base_url: str
    api_key_env: str
    api_key_configured: bool
    timeout_s: float
    max_retries: int
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class SoftwareEnvironment:
    geant4_install_dir: str
    geant4_config_bin: str
    geant4_setup_script: str
    cmake_bin: str
    ngspice_bin: str
    tcad_install_dir: str
    tcad_docker_container: str
    tcad_sde_bin: str
    tcad_svisual_bin: str
    tcad_swb_bin: str
    tcad_inspect_bin: str
    python_bin: str


@dataclass(frozen=True)
class RadAgentEnvironment:
    model_provider: ModelProvider
    proxy: str
    workspace_root: str
    rag_endpoints: dict[str, str]
    models: dict[ModelTier, ModelTierEnvironment]
    software: SoftwareEnvironment


def _provider_from_env() -> ModelProvider:
    provider = _env("RADAGENT_MODEL_PROVIDER", "openai_compatible").lower()
    if provider == "mock":
        return ModelProvider.MOCK
    return ModelProvider.OPENAI_COMPATIBLE


def _model_tier(
    tier: ModelTier,
    model_env: str,
    default_model: str,
    timeout_env: str,
    default_timeout: float,
    max_tokens_env: str,
    default_max_tokens: int,
    max_retries_env: str,
    default_max_retries: int,
    temperature_env: str,
    default_temperature: float,
    api_key_env_var: str,
) -> ModelTierEnvironment:
    provider = _provider_from_env()
    base_url = _env(
        f"RADAGENT_{tier.value.upper()}_BASE_URL",
        _env("RADAGENT_MODEL_BASE_URL", ""),
    )
    api_key_env = _env(api_key_env_var, "RADAGENT_API_KEY")
    return ModelTierEnvironment(
        tier=tier,
        provider=provider,
        model_name=_env(model_env, default_model),
        base_url=base_url,
        api_key_env=api_key_env,
        api_key_configured=bool(_env(api_key_env)),
        timeout_s=_env_float(timeout_env, default_timeout),
        max_retries=_env_int(max_retries_env, default_max_retries),
        temperature=_env_float(temperature_env, default_temperature),
        max_tokens=_env_int(max_tokens_env, default_max_tokens),
    )


def load_environment(env_path: Path | None = None) -> RadAgentEnvironment:
    """Load the complete RadAgent environment configuration."""
    load_project_env(env_path)

    geant4_install_dir = _path_env("GEANT4_INSTALL_DIR", "/usr/local/geant4")
    geant4_config_default = (
        str(Path(geant4_install_dir) / "bin" / "geant4-config")
        if geant4_install_dir
        else _which("geant4-config")
    )
    software = SoftwareEnvironment(
        geant4_install_dir=geant4_install_dir,
        geant4_config_bin=_path_env("GEANT4_CONFIG_BIN", geant4_config_default),
        geant4_setup_script=_path_env("GEANT4_SETUP_SCRIPT", "/etc/profile.d/geant4.sh"),
        cmake_bin=_path_env("CMAKE_BIN", _which("cmake")),
        ngspice_bin=_path_env("NGSPICE_BIN", _which("ngspice")),
        tcad_install_dir=_path_env("TCAD_INSTALL_DIR", _env("STROOT", "")),
        tcad_docker_container=_env("TCAD_DOCKER_CONTAINER", "tcad-sentaurus"),
        tcad_sde_bin=_path_env("TCAD_SDE_BIN", _which("sde")),
        tcad_svisual_bin=_path_env("TCAD_SVISUAL_BIN", _which("svisual")),
        tcad_swb_bin=_path_env("TCAD_SWB_BIN", _which("swb")),
        tcad_inspect_bin=_path_env("TCAD_INSPECT_BIN", _which("inspect")),
        python_bin=_path_env("PYTHON_BIN", sys.executable),
    )

    models = {
        ModelTier.LITE: _model_tier(
            ModelTier.LITE,
            "RADAGENT_MODEL_LITE",
            "deepseek-v4-flash",
            "RADAGENT_LITE_TIMEOUT_S",
            30.0,
            "RADAGENT_LITE_MAX_TOKENS",
            2048,
            "RADAGENT_LITE_MAX_RETRIES",
            2,
            "RADAGENT_LITE_TEMPERATURE",
            0.0,
            "RADAGENT_LITE_API_KEY_ENV",
        ),
        ModelTier.PRO: _model_tier(
            ModelTier.PRO,
            "RADAGENT_MODEL_PRO",
            "deepseek-v4-pro",
            "RADAGENT_PRO_TIMEOUT_S",
            90.0,
            "RADAGENT_PRO_MAX_TOKENS",
            8192,
            "RADAGENT_PRO_MAX_RETRIES",
            2,
            "RADAGENT_PRO_TEMPERATURE",
            0.0,
            "RADAGENT_PRO_API_KEY_ENV",
        ),
        ModelTier.MAX: _model_tier(
            ModelTier.MAX,
            "RADAGENT_MODEL_MAX",
            "deepseek-v4-pro",
            "RADAGENT_MAX_TIMEOUT_S",
            120.0,
            "RADAGENT_MAX_TOKENS",
            12000,
            "RADAGENT_MAX_MAX_RETRIES",
            2,
            "RADAGENT_MAX_TEMPERATURE",
            0.0,
            "RADAGENT_MAX_API_KEY_ENV",
        ),
    }

    return RadAgentEnvironment(
        model_provider=_provider_from_env(),
        proxy=_env("RADAGENT_PROXY", ""),
        workspace_root=_path_env("RADAGENT_WORKSPACE_ROOT", _env("SIMULATION_WORKSPACE", "")),
        rag_endpoints={
            "geant4": _env("GEANT4_RAG_ENDPOINT", ""),
            "tcad": _env("TCAD_RAG_ENDPOINT", ""),
            "spice": _env("SPICE_RAG_ENDPOINT", ""),
        },
        models=models,
        software=software,
    )


def validate_acceptance_environment(
    *,
    require_model: bool = True,
    require_geant4: bool = True,
    require_tcad: bool = False,
) -> tuple[bool, list[str]]:
    """Validate required external environment for acceptance runs."""
    env = load_environment()
    errors: list[str] = []

    if require_model:
        for tier_name, tier in env.models.items():
            if tier.provider != ModelProvider.MOCK:
                if not tier.base_url:
                    errors.append(f"{tier_name.value}: missing model base URL")
                if not tier.api_key_configured:
                    errors.append(f"{tier_name.value}: missing API key env {tier.api_key_env}")

    if require_geant4:
        if not Path(env.software.geant4_config_bin).is_file():
            errors.append(f"missing geant4-config: {env.software.geant4_config_bin}")
        if not env.software.cmake_bin:
            errors.append("missing cmake executable")

    if require_tcad:
        tcad_available = any(
            [
                env.software.tcad_install_dir,
                env.software.tcad_sde_bin,
                env.software.tcad_svisual_bin,
                env.software.tcad_swb_bin,
            ]
        )
        if not tcad_available:
            errors.append("missing TCAD installation/tool paths")

    return (not errors, errors)
