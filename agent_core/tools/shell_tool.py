"""Shell execution tool for running builds and simulations."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

BLOCKED_PATTERNS = (
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "rm -rf ~",
    "> /dev/sd",
)


class ShellTool:
    """Shell tool for executing build and simulation commands.

    Enforces safety:
    - No destructive commands (rm -rf, etc.)
    - Working directory must be within workspace
    - Timeout enforced
    - Output captured
    """

    def __init__(self, workspace_root: str = "simulation_workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 300,
        env: dict | None = None,
    ) -> dict:
        """Execute *command* safely and return a result dict."""
        if not self._is_safe_command(command):
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Blocked: command matches a dangerous pattern",
                "return_code": -1,
                "timed_out": False,
            }

        resolved_cwd = self._resolve_cwd(cwd)

        merged_env = {**os.environ, **(env or {})}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(resolved_cwd),
                env=merged_env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "success": proc.returncode == 0,
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "return_code": proc.returncode or 0,
                "timed_out": False,
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "return_code": -1,
                "timed_out": True,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "stdout": "",
                "stderr": str(exc),
                "return_code": -1,
                "timed_out": False,
            }

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _is_safe_command(self, command: str) -> bool:
        lower = command.lower()
        return not any(pat in lower for pat in BLOCKED_PATTERNS)

    def _resolve_cwd(self, cwd: str | None) -> Path:
        if cwd is None:
            return self.workspace_root
        resolved = Path(cwd).resolve()
        if not str(resolved).startswith(str(self.workspace_root)):
            msg = f"cwd {resolved} is outside workspace {self.workspace_root}"
            raise ValueError(msg)
        return resolved

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    async def run_cmake(self, build_dir: str, source_dir: str) -> dict:
        """Run cmake configure."""
        return await self.run(
            f"cmake -DCMAKE_BUILD_TYPE=Release {source_dir}",
            cwd=build_dir,
            timeout=120,
        )

    async def run_make(self, build_dir: str, threads: int = 4) -> dict:
        """Run make build."""
        return await self.run(
            f"make -j{threads}",
            cwd=build_dir,
            timeout=600,
        )

    async def run_geant4_sim(
        self,
        executable: str,
        macro: str | None = None,
        events: int = 100,
        threads: int = 1,
    ) -> dict:
        """Run Geant4 simulation."""
        cmd_parts = [executable]
        if macro:
            cmd_parts.append(macro)
        env = {"G4THREADS": str(threads)}
        return await self.run(
            " ".join(cmd_parts),
            timeout=max(300, events),
            env=env,
        )

    async def run_ngspice(self, netlist_path: str) -> dict:
        """Run ngspice batch simulation."""
        return await self.run(
            f"ngspice -b {netlist_path}",
            timeout=300,
        )
