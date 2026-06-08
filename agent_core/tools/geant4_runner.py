"""Geant4 simulation runner — cmake configure, build, run, collect outputs."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from agent_core.config.environment import load_environment

logger = logging.getLogger(__name__)


class Geant4Runner:
    """Runs Geant4 simulations with proper environment setup.

    Handles: cmake configure, build, run simulation, collect outputs.
    Detects if Geant4 is available locally.
    """

    def __init__(self, geant4_dir: str | None = None) -> None:
        env = load_environment()
        self.geant4_dir = geant4_dir or env.software.geant4_install_dir
        self.geant4_config_bin = env.software.geant4_config_bin
        self.geant4_setup_script = env.software.geant4_setup_script
        self.geant4_available = self._check_geant4()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_geant4(self) -> bool:
        config = Path(self.geant4_config_bin)
        if config.is_file() and os.access(config, os.X_OK):
            return True
        install_config = Path(self.geant4_dir) / "bin" / "geant4-config"
        if install_config.is_file() and os.access(install_config, os.X_OK):
            return True
        alt = shutil.which("geant4-config")
        return alt is not None

    async def _run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        """Execute *cmd* inside a bash login shell (sources geant4.sh)."""
        g4_script = Path(self.geant4_setup_script)
        setup = f"source {self.geant4_setup_script} 2>/dev/null; " if g4_script.is_file() else ""
        proc = await asyncio.create_subprocess_shell(
            setup + cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def configure(self, source_dir: str, build_dir: str) -> dict[str, Any]:
        """Run cmake configure. Returns {success, cmake_output, errors}."""
        Path(build_dir).mkdir(parents=True, exist_ok=True)
        rc, out, err = await self._run(f"cmake {source_dir}", cwd=build_dir)
        return {"success": rc == 0, "cmake_output": out, "errors": err}

    async def build(self, build_dir: str, threads: int = 4) -> dict[str, Any]:
        """Run make. Returns {success, build_output, executable_path, errors}."""
        rc, out, err = await self._run(f"make -j{threads}", cwd=build_dir)
        exe: str | None = None
        if rc == 0:
            candidates = (
                list(Path(build_dir).glob("*.exe"))
                + list(Path(build_dir).glob("*_sim"))
                + [p for p in Path(build_dir).iterdir() if p.is_file() and os.access(p, os.X_OK)]
            )
            exe = str(candidates[0]) if candidates else None
        return {"success": rc == 0, "build_output": out, "executable_path": exe, "errors": err}

    async def simulate(
        self,
        executable: str,
        macro: str | None = None,
        events: int = 100,
        threads: int = 1,
        output_dir: str | None = None,
        job_id: str = "unknown",
    ) -> dict[str, Any]:
        """Run simulation. Macro passed as positional arg per project convention."""
        cmd = executable
        if macro:
            cmd += f" {macro}"
        env_prefix = ""
        if threads > 1:
            env_prefix += f"export G4FORCE_RUN_MANAGER_THREAD={threads}; "
        if output_dir:
            env_prefix += f"export G4_OUTPUT_DIR={output_dir}; "
        if job_id != "unknown":
            env_prefix += f"export G4_JOB_ID={job_id}; "
        rc, out, err = await self._run(env_prefix + cmd)
        return {
            "success": rc == 0,
            "output_dir": output_dir or str(Path(executable).parent),
            "log": out,
            "errors": err,
        }

    async def smoke_test(
        self,
        project_dir: str,
        *,
        job_id: str = "unknown",
        output_dir: str | None = None,
        events: int = 10,
    ) -> dict[str, Any]:
        """Quick smoke test: configure + build + run with few events.

        If Geant4 is not available, returns success=False (structure_check
        does NOT count as a build pass).
        """
        if not self.geant4_available:
            return {
                "success": False,
                "has_geant4": False,
                "output_summary": None,
                "warnings": ["Geant4 not available — structure_check does not verify build"],
            }

        # Resolve output dir
        _output_dir = output_dir or str(Path(project_dir) / "build" / "output")
        Path(_output_dir).mkdir(parents=True, exist_ok=True)

        build_dir = str(Path(project_dir) / "build")
        cfg = await self.configure(project_dir, build_dir)
        if not cfg["success"]:
            return {
                "success": False,
                "has_geant4": True,
                "output_summary": None,
                "warnings": [cfg["errors"]],
            }

        bld = await self.build(build_dir)
        if not bld["success"] or not bld["executable_path"]:
            return {
                "success": False,
                "has_geant4": True,
                "output_summary": None,
                "warnings": [bld["errors"]],
            }

        macro_path = Path(project_dir) / "macros" / "run.mac"
        sim = await self.simulate(
            bld["executable_path"],
            macro=str(macro_path) if macro_path.is_file() else None,
            events=events,
            output_dir=_output_dir,
            job_id=job_id,
        )
        return {
            "success": sim["success"],
            "has_geant4": True,
            "output_dir": _output_dir,
            "output_summary": sim["log"][-500:] if sim["log"] else "",
            "warnings": [sim["errors"]] if sim["errors"] else [],
        }

    async def structure_check(self, project_dir: str) -> dict[str, Any]:
        """Check project structure without building.

        Verifies CMakeLists.txt, src/, include/ exist and parses CMakeLists.txt.
        """
        root = Path(project_dir)
        issues: list[str] = []

        if not (root / "CMakeLists.txt").is_file():
            issues.append("Missing CMakeLists.txt")
        else:
            text = (root / "CMakeLists.txt").read_text(errors="replace")
            for required in ("find_package(Geant4", "add_executable"):
                if required not in text:
                    issues.append(f"CMakeLists.txt missing '{required}'")

        for dirname in ("src", "include"):
            if not (root / dirname).is_dir():
                issues.append(f"Missing '{dirname}/' directory")

        return {"valid": len(issues) == 0, "issues": issues}
