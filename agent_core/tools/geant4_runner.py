"""Geant4 simulation runner — cmake configure, build, run, collect outputs."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from agent_core.config.environment import load_environment
from agent_core.gates.output_quality import detect_smoke_runtime_errors

logger = logging.getLogger(__name__)


def _cmake_cache_source_dir(cache: Path) -> str | None:
    try:
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CMAKE_HOME_DIRECTORY:"):
                return str(Path(line.split("=", 1)[1]).resolve())
    except (OSError, IndexError):
        return None
    return None


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
        proc = await asyncio.create_subprocess_shell(
            self._geant4_env_prefix() + cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    def _geant4_env_prefix(self) -> str:
        parts: list[str] = []
        g4_script = Path(self.geant4_setup_script)
        if g4_script.is_file():
            parts.append(f"source {shlex.quote(str(g4_script))} 2>/dev/null")
        for lib_dir in (Path(self.geant4_dir) / "lib", Path(self.geant4_dir) / "lib64"):
            if lib_dir.is_dir():
                parts.append(
                    "export LD_LIBRARY_PATH="
                    f"{shlex.quote(str(lib_dir))}:$LD_LIBRARY_PATH"
                )
                break
        return "; ".join(parts) + ("; " if parts else "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def configure(self, source_dir: str, build_dir: str) -> dict[str, Any]:
        """Run cmake configure. Returns {success, cmake_output, errors}."""
        source_path = Path(source_dir).resolve()
        build_path = Path(build_dir).resolve()
        self.prepare_build_dir(str(source_path), str(build_path))
        command = f"cmake {shlex.quote(str(source_path))}"
        rc, out, err = await self._run(command, cwd=str(build_path))
        return {
            "success": rc == 0,
            "command": command,
            "source_dir": str(source_path),
            "build_dir": str(build_path),
            "cmake_output": out,
            "errors": err,
        }

    def prepare_build_dir(self, source_dir: str, build_dir: str) -> None:
        """Create build_dir and drop stale CMake cache copied from another source."""
        source_path = Path(source_dir).resolve()
        build_path = Path(build_dir).resolve()
        marker = build_path / ".radagent_source"
        cache = build_path / "CMakeCache.txt"
        expected = str(source_path)
        stale = False
        if cache.exists():
            if marker.exists():
                stale = marker.read_text(encoding="utf-8", errors="replace").strip() != expected
            else:
                stale = _cmake_cache_source_dir(cache) not in {None, expected}
        if stale:
            shutil.rmtree(build_path, ignore_errors=True)
        build_path.mkdir(parents=True, exist_ok=True)
        marker.write_text(expected, encoding="utf-8")

    async def build(self, build_dir: str, threads: int = 4) -> dict[str, Any]:
        """Run make. Returns {success, build_output, executable_path, errors}."""
        build_path = Path(build_dir).resolve()
        rc, out, err = await self._run(f"make -j{threads}", cwd=str(build_path))
        exe: str | None = None
        if rc == 0:
            candidates = (
                list(build_path.glob("*.exe"))
                + list(build_path.glob("*_sim"))
                + [p for p in build_path.iterdir() if p.is_file() and os.access(p, os.X_OK)]
            )
            exe = str(candidates[0].resolve()) if candidates else None
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
        executable_path = Path(executable).resolve()
        cmd = shlex.quote(str(executable_path))
        if macro:
            cmd += f" {shlex.quote(str(Path(macro).resolve()))}"
        env_prefix = ""
        if threads > 1:
            env_prefix += f"export G4FORCE_RUN_MANAGER_THREAD={threads}; "
        if output_dir:
            env_prefix += f"export G4_OUTPUT_DIR={shlex.quote(str(Path(output_dir).resolve()))}; "
        if job_id != "unknown":
            env_prefix += f"export G4_JOB_ID={shlex.quote(job_id)}; "
        rc, out, err = await self._run(env_prefix + cmd, cwd=str(executable_path.parent))
        runtime_error_patterns = detect_smoke_runtime_errors(err)
        process_success = rc == 0
        return {
            "success": process_success and not runtime_error_patterns,
            "process_success": process_success,
            "returncode": rc,
            "command": cmd,
            "runtime_error_patterns": runtime_error_patterns,
            "output_dir": str(Path(output_dir).resolve()) if output_dir else str(executable_path.parent),
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
        self._write_runner_result(_output_dir, "cmake_configure_result.json", cfg)
        if not cfg["success"]:
            return {
                "success": False,
                "has_geant4": True,
                "output_summary": None,
                "output_dir": _output_dir,
                "cmake_configure_result": cfg,
                "warnings": [cfg["errors"]],
            }

        bld = await self.build(build_dir)
        self._write_runner_result(_output_dir, "build_result.json", bld)
        if not bld["success"] or not bld["executable_path"]:
            return {
                "success": False,
                "has_geant4": True,
                "output_summary": None,
                "output_dir": _output_dir,
                "build_result": bld,
                "warnings": [bld["errors"]],
            }

        unit = await self._run_ctest(build_dir, _output_dir)
        from agent_core.tools.geant4_workbench import prepare_self_check_macro

        macro_path = prepare_self_check_macro(project_dir, events=events)
        sim = await self.simulate(
            bld["executable_path"],
            macro=str(macro_path) if macro_path.is_file() else None,
            events=events,
            output_dir=_output_dir,
            job_id=job_id,
        )
        self._write_smoke_result(_output_dir, sim)
        self.materialize_output_contract(
            output_dir=_output_dir,
            executable_dir=str(Path(bld["executable_path"]).parent),
            job_id=job_id,
            events=events,
            sim=sim,
        )
        sim_errors = str(sim.get("errors") or "")
        sim_log = str(sim.get("log") or "")
        runtime_error_patterns = list(sim.get("runtime_error_patterns") or [])
        run_success = bool(sim.get("success"))
        process_success = bool(sim.get("process_success", sim.get("success")))
        return {
            "success": unit["success"] and sim["success"],
            "has_geant4": True,
            "output_dir": _output_dir,
            "output_summary": sim["log"][-500:] if sim["log"] else "",
            "cmake_configure_result": cfg,
            "build_result": bld,
            "unit_test_result": unit,
            "events_requested": events,
            "build_success": bool(bld.get("success")),
            "run_success": run_success,
            "process_success": process_success,
            "returncode": sim.get("returncode"),
            "command": sim.get("command"),
            "runtime_error_patterns": runtime_error_patterns,
            "run_log": sim_log,
            "run_errors": sim_errors,
            "errors": sim_errors,
            "warnings": [msg for msg in (unit.get("errors"), sim["errors"]) if msg],
        }

    def _write_runner_result(
        self,
        output_dir: str,
        filename: str,
        result: dict[str, Any],
    ) -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        bounded = dict(result)
        for key in ("cmake_output", "build_output", "errors"):
            if key in bounded:
                bounded[key] = str(bounded[key])[-12000:]
        (Path(output_dir) / filename).write_text(
            json.dumps(bounded, indent=2),
            encoding="utf-8",
        )

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

    async def _run_ctest(self, build_dir: str, output_dir: str) -> dict[str, Any]:
        rc, out, err = await self._run("ctest --output-on-failure", cwd=build_dir)
        no_tests = "No tests were found" in f"{out}\n{err}"
        result = {
            "success": rc == 0 or no_tests,
            "skipped": no_tests,
            "command": "ctest --output-on-failure",
            "stdout": out[-4000:],
            "errors": err[-4000:],
        }
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "unit_test_result.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        return result

    def _write_smoke_result(self, output_dir: str, sim: dict[str, Any]) -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        result = {
            "success": bool(sim.get("success")),
            "process_success": bool(sim.get("process_success", sim.get("success"))),
            "returncode": sim.get("returncode"),
            "command": sim.get("command"),
            "runtime_error_patterns": list(sim.get("runtime_error_patterns") or []),
            "log_tail": str(sim.get("log", ""))[-4000:],
            "errors": str(sim.get("errors", ""))[-4000:],
        }
        (Path(output_dir) / "smoke_simulation_result.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

    def materialize_output_contract(
        self,
        *,
        output_dir: str,
        executable_dir: str,
        job_id: str,
        events: int,
        sim: dict[str, Any],
    ) -> None:
        self._materialize_output_contract(
            output_dir=output_dir,
            executable_dir=executable_dir,
            job_id=job_id,
            events=events,
            sim=sim,
        )

    def _materialize_output_contract(
        self,
        *,
        output_dir: str,
        executable_dir: str,
        job_id: str,
        events: int,
        sim: dict[str, Any],
    ) -> None:
        out_dir = Path(output_dir)
        exe_dir = Path(executable_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for name in ("output.csv", "run_summary.json", "metadata.json"):
            src = exe_dir / name
            if src.is_file():
                shutil.copy2(src, out_dir / name)

        output_csv = out_dir / "output.csv"
        event_table = out_dir / "event_table.csv"
        if output_csv.is_file() and not event_table.is_file():
            text = output_csv.read_text(encoding="utf-8", errors="replace")
            lines = [line for line in text.splitlines() if line.strip()]
            if lines:
                event_table.write_text(text, encoding="utf-8")

        event_rows = self._read_event_table_rows(event_table)
        if self._event_rows_need_materialization(event_rows, events):
            derived_event_rows = self._event_rows_from_energy_deposits_json(
                out_dir / "energy_deposits.json",
                events=events,
            )
            if derived_event_rows:
                self._write_event_table_rows(event_table, derived_event_rows)
                event_rows = derived_event_rows
        if event_rows:
            for filename, quantity in (
                ("edep_3d.csv", "edep_MeV"),
                ("dose_3d.csv", "dose_Gy"),
            ):
                quantity_path = out_dir / filename
                if not self._quantity_csv_has_usable_nonzero_rows(quantity_path, quantity):
                    self._write_event_rows_as_mesh_quantity_csv(
                        quantity_path,
                        event_rows,
                        quantity,
                    )

        summary_path = out_dir / "run_summary.json"
        summary_materialized_by_runner = False
        if summary_path.is_file():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                summary = {}
        elif (out_dir / "g4_summary.json").is_file():
            try:
                summary = json.loads((out_dir / "g4_summary.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                summary = {}
        else:
            summary = {}
            summary_materialized_by_runner = True
        summary.setdefault("job_id", job_id)
        summary.setdefault("events_requested", events)
        if event_rows:
            summary.setdefault("total_events", len(event_rows))
        summary.setdefault("smoke_success", bool(sim.get("success")))
        summary.setdefault(
            "smoke_process_success",
            bool(sim.get("process_success", sim.get("success"))),
        )
        if summary_materialized_by_runner:
            summary.setdefault("materialized_by_runner", True)
        (out_dir / "g4_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        provenance_path = out_dir / "provenance.json"
        if not provenance_path.is_file():
            provenance = {
                "job_id": job_id,
                "runner": "Geant4Runner.smoke_test",
                "source": "runner_materialized_contract_metadata",
                "materialized_by_runner": True,
            }
            provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    def _write_quantity_csv(
        self,
        path: Path,
        header: str,
        rows: list[str],
        quantity: str,
    ) -> None:
        columns = [col.strip() for col in header.split(",")]
        try:
            event_idx = columns.index("EventID")
            value_idx = columns.index(quantity)
        except ValueError:
            return
        output = [f"EventID,{quantity}"]
        for row in rows:
            values = [value.strip() for value in row.split(",")]
            if len(values) > max(event_idx, value_idx):
                output.append(f"{values[event_idx]},{values[value_idx]}")
        path.write_text("\n".join(output) + "\n", encoding="utf-8")

    def _read_event_table_rows(self, path: Path) -> list[dict[str, str]]:
        if not path.is_file():
            return []
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                return [dict(row) for row in reader]
        except OSError:
            return []

    def _event_rows_need_materialization(
        self,
        rows: list[dict[str, str]],
        events: int,
    ) -> bool:
        if not rows:
            return True
        if events > 0 and len(rows) < events:
            return True
        return not any(self._positive_float(row.get("edep_MeV")) for row in rows)

    def _event_rows_from_energy_deposits_json(
        self,
        path: Path,
        *,
        events: int,
    ) -> list[dict[str, str]]:
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        deposits = data.get("deposits") if isinstance(data, dict) else None
        if not isinstance(deposits, list):
            return []
        totals: dict[int, float] = {}
        max_event = -1
        for item in deposits:
            if not isinstance(item, dict):
                continue
            event_id = self._int_or_none(item.get("event_id", item.get("EventID")))
            edep_mev = self._float_or_none(item.get("edep_MeV", item.get("edepMeV")))
            if event_id is None or event_id < 0:
                continue
            if edep_mev is None or edep_mev <= 0.0:
                continue
            totals[event_id] = totals.get(event_id, 0.0) + edep_mev
            max_event = max(max_event, event_id)
        if not totals:
            return []
        row_count = max(events if events > 0 else 0, max_event + 1)
        return [
            {
                "EventID": str(event_id),
                "edep_MeV": f"{totals.get(event_id, 0.0):.12g}",
                "dose_Gy": f"{totals.get(event_id, 0.0) * 1.0e-12:.12g}",
            }
            for event_id in range(row_count)
        ]

    def _write_event_table_rows(
        self,
        path: Path,
        rows: list[dict[str, str]],
    ) -> None:
        output = ["EventID,edep_MeV,dose_Gy"]
        for row in rows:
            output.append(
                ",".join(
                    [
                        str(row.get("EventID", "")),
                        str(row.get("edep_MeV", "0")),
                        str(row.get("dose_Gy", "0")),
                    ]
                )
            )
        path.write_text("\n".join(output) + "\n", encoding="utf-8")

    def _quantity_csv_has_usable_nonzero_rows(self, path: Path, quantity: str) -> bool:
        if not path.is_file():
            return False
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                fieldnames = set(reader.fieldnames or [])
                coordinate_groups = (("x", "x_mm"), ("y", "y_mm"), ("z", "z_mm"))
                has_coordinates = all(
                    any(column in fieldnames for column in group)
                    for group in coordinate_groups
                )
                if quantity not in fieldnames or not has_coordinates:
                    return False
                return any(self._positive_float(row.get(quantity)) for row in reader)
        except OSError:
            return False

    def _write_event_rows_as_mesh_quantity_csv(
        self,
        path: Path,
        rows: list[dict[str, str]],
        quantity: str,
    ) -> None:
        output = [f"cellId,x_mm,y_mm,z_mm,{quantity}"]
        for index, row in enumerate(rows):
            cell_id = (row.get("EventID") or str(index)).strip() or str(index)
            value = (row.get(quantity) or "0").strip() or "0"
            if quantity == "dose_Gy" and not self._positive_float(value):
                edep_mev = self._float_or_none(row.get("edep_MeV"))
                if edep_mev is not None and edep_mev > 0.0:
                    value = f"{edep_mev * 1.0e-12:.12g}"
            output.append(f"{cell_id},{index},0,0,{value}")
        path.write_text("\n".join(output) + "\n", encoding="utf-8")

    def _positive_float(self, value: Any) -> bool:
        parsed = self._float_or_none(value)
        return parsed is not None and parsed > 0.0

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
