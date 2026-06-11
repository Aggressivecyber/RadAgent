"""Central RadAgent environment configuration.

This module is the single read surface for model endpoints, model names,
API-key env var names, RAG endpoints, and local simulation tool locations.
It intentionally reports whether secrets are configured without exposing
secret values.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from agent_core.models.schemas import ModelProvider, ModelTier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_MODEL_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL_LITE = "mimo-v2.5"
DEFAULT_MODEL_PRO = "mimo-v2.5-pro"
DEFAULT_MODEL_MAX = DEFAULT_MODEL_PRO
DEFAULT_CONTEXT_WINDOW_LITE = 32_000
DEFAULT_CONTEXT_WINDOW_PRO = 128_000
DEFAULT_CONTEXT_WINDOW_MAX = 128_000
_ENV_ASSIGNMENT_RE = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=).*$")


def load_project_env(env_path: Path | None = None) -> None:
    """Load project .env values without overriding exported shell values."""
    load_dotenv(env_path or DEFAULT_ENV_PATH, override=False)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def model_endpoint_requires_api_key(base_url: str | None) -> bool:
    """Return whether the configured model endpoint needs a local API key."""
    return bool(base_url)


def write_project_env_values(
    values: dict[str, str],
    *,
    env_path: Path | None = None,
    update_process_env: bool = True,
) -> Path:
    """Upsert selected values in the project .env file.

    This intentionally handles only simple KEY=value environment files. Existing
    comments and unknown lines are preserved, and changed values are also loaded
    into the current process so frontend edits take effect immediately.
    """
    target = env_path or DEFAULT_ENV_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    normalized = {key: str(value) for key, value in values.items() if key}
    seen: set[str] = set()
    output: list[str] = []
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    for line in lines:
        match = _ENV_ASSIGNMENT_RE.match(line)
        if not match:
            output.append(line)
            continue
        key = match.group(2)
        if key not in normalized:
            output.append(line)
            continue
        output.append(f"{match.group(1)}{key}{match.group(3)}{_format_env_value(normalized[key])}")
        seen.add(key)

    missing = [key for key in normalized if key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={_format_env_value(normalized[key])}")

    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")

    if update_process_env:
        for key, value in normalized.items():
            os.environ[key] = value

    return target


def _format_env_value(value: str) -> str:
    if value == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,\-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
    context_window_tokens: int


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
class ConcurrencyEnvironment:
    cpu_count: int
    memory_total_gb: float
    g4_module_max_concurrency: int
    scenario_max_concurrency: int


@dataclass(frozen=True)
class RadAgentEnvironment:
    proxy: str
    workspace_root: str
    rag_endpoints: dict[str, str]
    models: dict[ModelTier, ModelTierEnvironment]
    software: SoftwareEnvironment
    concurrency: ConcurrencyEnvironment


def _model_tier(
    tier: ModelTier,
    model_env: str,
    default_model: str,
    timeout_env: str,
    default_timeout: float,
    max_tokens_env: str,
    default_max_tokens: int,
    context_window_env: str,
    default_context_window_tokens: int,
    max_retries_env: str,
    default_max_retries: int,
    temperature_env: str,
    default_temperature: float,
    api_key_env_var: str,
) -> ModelTierEnvironment:
    base_url = _env(
        f"RADAGENT_{tier.value.upper()}_BASE_URL",
        _env("RADAGENT_MODEL_BASE_URL", DEFAULT_MODEL_BASE_URL),
    )
    api_key_env = _env(api_key_env_var, "RADAGENT_API_KEY")
    api_key_configured = bool(_env(api_key_env))
    return ModelTierEnvironment(
        tier=tier,
        provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name=_env(model_env, default_model),
        base_url=base_url,
        api_key_env=api_key_env,
        api_key_configured=api_key_configured,
        timeout_s=_env_float(timeout_env, default_timeout),
        max_retries=_env_int(max_retries_env, default_max_retries),
        temperature=_env_float(temperature_env, default_temperature),
        max_tokens=_env_int(max_tokens_env, default_max_tokens),
        context_window_tokens=_env_int(
            context_window_env,
            default_context_window_tokens,
        ),
    )


def _total_memory_gb() -> float:
    memory_from_sysconf = _total_memory_gb_from_sysconf()
    if memory_from_sysconf:
        return memory_from_sysconf

    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    return round(int(parts[1]) / (1024**2), 2)
    return 0.0


def _total_memory_gb_from_sysconf() -> float:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        if isinstance(page_size, int) and isinstance(page_count, int):
            return round((page_size * page_count) / (1024**3), 2)
    except (OSError, ValueError, AttributeError):
        return 0.0
    return 0.0


def resolve_safe_concurrency(
    workload_count: int,
    *,
    override_env: str,
    hard_cap: int,
    memory_per_worker_gb: float,
) -> int:
    """Return a bounded concurrency level from env override and host resources."""
    if workload_count <= 0:
        return 1

    override = _env_int(override_env, 0)
    if override > 0:
        return max(1, min(workload_count, override))

    cpu_count = os.cpu_count() or 1
    memory_total_gb = _total_memory_gb()
    cpu_based = max(1, cpu_count // 2)
    mem_based = (
        max(1, int(memory_total_gb // memory_per_worker_gb))
        if memory_total_gb > 0 and memory_per_worker_gb > 0
        else cpu_based
    )
    return max(1, min(workload_count, hard_cap, cpu_based, mem_based))


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
            DEFAULT_MODEL_LITE,
            "RADAGENT_LITE_TIMEOUT_S",
            30.0,
            "RADAGENT_LITE_MAX_TOKENS",
            2048,
            "RADAGENT_LITE_CONTEXT_WINDOW_TOKENS",
            DEFAULT_CONTEXT_WINDOW_LITE,
            "RADAGENT_LITE_MAX_RETRIES",
            2,
            "RADAGENT_LITE_TEMPERATURE",
            0.0,
            "RADAGENT_LITE_API_KEY_ENV",
        ),
        ModelTier.PRO: _model_tier(
            ModelTier.PRO,
            "RADAGENT_MODEL_PRO",
            DEFAULT_MODEL_PRO,
            "RADAGENT_PRO_TIMEOUT_S",
            240.0,
            "RADAGENT_PRO_MAX_TOKENS",
            8192,
            "RADAGENT_PRO_CONTEXT_WINDOW_TOKENS",
            DEFAULT_CONTEXT_WINDOW_PRO,
            "RADAGENT_PRO_MAX_RETRIES",
            2,
            "RADAGENT_PRO_TEMPERATURE",
            0.0,
            "RADAGENT_PRO_API_KEY_ENV",
        ),
        ModelTier.MAX: _model_tier(
            ModelTier.MAX,
            "RADAGENT_MODEL_MAX",
            DEFAULT_MODEL_MAX,
            "RADAGENT_MAX_TIMEOUT_S",
            300.0,
            "RADAGENT_MAX_MAX_TOKENS",
            12000,
            "RADAGENT_MAX_CONTEXT_WINDOW_TOKENS",
            DEFAULT_CONTEXT_WINDOW_MAX,
            "RADAGENT_MAX_MAX_RETRIES",
            2,
            "RADAGENT_MAX_TEMPERATURE",
            0.0,
            "RADAGENT_MAX_API_KEY_ENV",
        ),
    }
    concurrency = ConcurrencyEnvironment(
        cpu_count=os.cpu_count() or 1,
        memory_total_gb=_total_memory_gb(),
        g4_module_max_concurrency=resolve_safe_concurrency(
            10,
            override_env="RADAGENT_G4_MODULE_MAX_CONCURRENCY",
            hard_cap=_env_int("RADAGENT_G4_MODULE_HARD_CAP", 4),
            memory_per_worker_gb=_env_float("RADAGENT_G4_MODULE_MEMORY_GB", 2.0),
        ),
        scenario_max_concurrency=resolve_safe_concurrency(
            32,
            override_env="RADAGENT_SCENARIO_MAX_CONCURRENCY",
            hard_cap=_env_int("RADAGENT_SCENARIO_HARD_CAP", 4),
            memory_per_worker_gb=_env_float("RADAGENT_SCENARIO_MEMORY_GB", 3.0),
        ),
    )

    return RadAgentEnvironment(
        proxy=_env("RADAGENT_PROXY", ""),
        workspace_root=_path_env("RADAGENT_WORKSPACE_ROOT", _env("SIMULATION_WORKSPACE", "")),
        rag_endpoints={
            "geant4": _env("GEANT4_RAG_ENDPOINT", ""),
            "tcad": _env("TCAD_RAG_ENDPOINT", ""),
            "spice": _env("SPICE_RAG_ENDPOINT", ""),
        },
        models=models,
        software=software,
        concurrency=concurrency,
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
            api_key_value = _env(tier.api_key_env)
            if not tier.base_url:
                errors.append(f"{tier_name.value}: missing model base URL")
            if model_endpoint_requires_api_key(tier.base_url) and not api_key_value:
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
