from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest
from agent_core.tools.geant4_runner import Geant4Runner
from agent_core.tools.geant4_workbench import (
    prepare_self_check_macro,
    prepare_visual_workbench,
    resolve_self_check_events,
    visual_workbench_environment,
)


def _runner() -> Geant4Runner:
    return Geant4Runner.__new__(Geant4Runner)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_prepare_self_check_macro_rewrites_beamon_count(tmp_path: Path) -> None:
    project_dir = tmp_path / "geant4_project"
    macros_dir = project_dir / "macros"
    macros_dir.mkdir(parents=True)
    (macros_dir / "run.mac").write_text(
        "/run/initialize\n/gun/particle proton\n/run/beamOn 10\n",
        encoding="utf-8",
    )

    macro_path = prepare_self_check_macro(project_dir, events=1000)

    assert macro_path == macros_dir / "radagent_self_check_1000.mac"
    text = macro_path.read_text(encoding="utf-8")
    assert "/run/beamOn 1000" in text
    assert "/run/beamOn 10" not in text.splitlines()


@pytest.mark.parametrize("event_key", ["events", "num_events", "requested_events"])
def test_resolve_self_check_events_accepts_source_event_aliases(event_key: str) -> None:
    g4_model_ir = {"sources": [{event_key: 11}, {event_key: "7"}]}

    assert resolve_self_check_events(g4_model_ir=g4_model_ir) == 18


def test_prepare_visual_workbench_writes_b1_b2_style_macros(tmp_path: Path) -> None:
    project_dir = tmp_path / "geant4_project"
    (project_dir / "macros").mkdir(parents=True)

    result = prepare_visual_workbench(
        project_dir,
        executable=project_dir / "build" / "sim",
        events=100,
    )

    init_vis = Path(result["init_macro"])
    vis = Path(result["vis_macro"])
    gui = Path(result["gui_macro"])
    init_alias = project_dir / "macros" / "init.mac"
    assert init_vis.name == "init_vis.mac"
    assert "/control/saveHistory" in init_vis.read_text(encoding="utf-8")
    assert "/control/execute macros/vis.mac" in init_vis.read_text(encoding="utf-8")
    assert init_alias.read_text(encoding="utf-8") == init_vis.read_text(encoding="utf-8")
    vis_text = vis.read_text(encoding="utf-8")
    assert "/vis/open" in vis_text
    assert "/vis/scene/add/trajectories smooth" in vis_text
    assert "/vis/scene/add/hits" in vis_text
    assert "/run/beamOn 100" in vis_text
    assert "/gui/addButton viewer" in gui.read_text(encoding="utf-8")
    assert result["events"] == 100
    assert result["launch_command"][-1] == str(project_dir / "build" / "sim")


def test_visual_workbench_environment_defaults_qt_to_xcb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("DISPLAY", ":7")

    env = visual_workbench_environment()

    assert env["QT_QPA_PLATFORM"] == "xcb"
    assert env["DISPLAY"] == ":7"


@pytest.mark.asyncio
async def test_runner_prepends_geant4_lib_to_ld_library_path(tmp_path: Path) -> None:
    runner = _runner()
    runner.geant4_setup_script = str(tmp_path / "geant4.sh")
    runner.geant4_dir = str(tmp_path / "geant4")
    (tmp_path / "geant4" / "lib").mkdir(parents=True)
    seen: dict[str, str] = {}

    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_shell(cmd: str, **kwargs: object) -> FakeProc:
        seen["cmd"] = cmd
        return FakeProc()

    import asyncio

    original = asyncio.create_subprocess_shell
    asyncio.create_subprocess_shell = fake_shell  # type: ignore[assignment]
    try:
        await runner._run("RadAgentG4")
    finally:
        asyncio.create_subprocess_shell = original  # type: ignore[assignment]

    assert f"export LD_LIBRARY_PATH={tmp_path / 'geant4' / 'lib'}" in seen["cmd"]
    assert "RadAgentG4" in seen["cmd"]


@pytest.mark.asyncio
async def test_configure_resolves_relative_source_before_running_from_build_dir(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    build_dir = project_dir / "build"
    project_dir.mkdir()
    runner = _runner()
    seen: dict[str, str | None] = {}

    async def fake_run(cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return 0, "", ""

    runner._run = fake_run  # type: ignore[method-assign]

    result = await runner.configure(
        os.path.relpath(project_dir, Path.cwd()),
        os.path.relpath(build_dir, Path.cwd()),
    )

    assert result["success"] is True
    assert seen["cmd"] == f"cmake {project_dir.resolve()}"
    assert seen["cwd"] == str(build_dir.resolve())
    assert result["command"] == f"cmake {project_dir.resolve()}"
    assert result["source_dir"] == str(project_dir.resolve())
    assert result["build_dir"] == str(build_dir.resolve())


@pytest.mark.asyncio
async def test_build_returns_absolute_executable_path_for_relative_build_dir(
    tmp_path: Path,
) -> None:
    build_dir = tmp_path / "geant4_project" / "build"
    build_dir.mkdir(parents=True)
    executable = build_dir / "RadAgent"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    runner = _runner()

    async def fake_run(cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        assert cmd == "make -j4"
        assert cwd == str(build_dir.resolve())
        return 0, "", ""

    runner._run = fake_run  # type: ignore[method-assign]

    result = await runner.build(os.path.relpath(build_dir, Path.cwd()))

    assert result["success"] is True
    assert result["executable_path"] == str(executable.resolve())


@pytest.mark.asyncio
async def test_simulate_resolves_relative_paths_before_running_from_executable_dir(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    build_dir = project_dir / "build"
    macros_dir = project_dir / "macros"
    output_dir = tmp_path / "out"
    build_dir.mkdir(parents=True)
    macros_dir.mkdir(parents=True)
    executable = build_dir / "RadAgent"
    macro = macros_dir / "run.mac"
    executable.write_text("", encoding="utf-8")
    macro.write_text("/run/beamOn 1\n", encoding="utf-8")
    runner = _runner()
    seen: dict[str, str | None] = {}

    async def fake_run(cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return 0, "", ""

    runner._run = fake_run  # type: ignore[method-assign]

    result = await runner.simulate(
        os.path.relpath(executable, Path.cwd()),
        macro=os.path.relpath(macro, Path.cwd()),
        output_dir=os.path.relpath(output_dir, Path.cwd()),
        job_id="job path",
    )

    assert result["success"] is True
    assert seen["cwd"] == str(build_dir.resolve())
    assert str(executable.resolve()) in str(seen["cmd"])
    assert str(macro.resolve()) in str(seen["cmd"])
    assert f"G4_OUTPUT_DIR={output_dir.resolve()}" in str(seen["cmd"])


def test_materialize_output_contract_derives_3d_outputs_from_event_table(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    executable_dir = tmp_path / "build"
    output_dir.mkdir()
    executable_dir.mkdir()
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.5,0.01\n1,0.25,0.002\n",
        encoding="utf-8",
    )

    _runner()._materialize_output_contract(
        output_dir=str(output_dir),
        executable_dir=str(executable_dir),
        job_id="job",
        events=2,
        sim={"success": True},
    )

    edep_rows = _read_rows(output_dir / "edep_3d.csv")
    dose_rows = _read_rows(output_dir / "dose_3d.csv")
    assert edep_rows[0]["x_mm"] == "0"
    assert edep_rows[0]["edep_MeV"] == "1.5"
    assert dose_rows[1]["z_mm"] == "0"
    assert dose_rows[1]["dose_Gy"] == "0.002"
    summary = json.loads((output_dir / "g4_summary.json").read_text(encoding="utf-8"))
    assert summary["total_events"] == 2
    assert summary["events_requested"] == 2


def test_materialize_output_contract_replaces_unusable_zero_3d_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    executable_dir = tmp_path / "build"
    output_dir.mkdir()
    executable_dir.mkdir()
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,2.0,0.02\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text("EventID,edep_MeV\n0,0\n", encoding="utf-8")
    (output_dir / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0\n", encoding="utf-8")

    _runner()._materialize_output_contract(
        output_dir=str(output_dir),
        executable_dir=str(executable_dir),
        job_id="job",
        events=1,
        sim={"success": True},
    )

    assert _read_rows(output_dir / "edep_3d.csv")[0]["edep_MeV"] == "2.0"
    assert _read_rows(output_dir / "dose_3d.csv")[0]["dose_Gy"] == "0.02"


def test_materialize_output_contract_rebuilds_bad_event_table_from_energy_deposits(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    executable_dir = tmp_path / "build"
    output_dir.mkdir()
    executable_dir.mkdir()
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,0.0,0.0\n",
        encoding="utf-8",
    )
    (output_dir / "energy_deposits.json").write_text(
        json.dumps(
            {
                "deposits": [
                    {"event_id": 0, "edep_MeV": 0.25},
                    {"event_id": 0, "edep_MeV": 0.75},
                    {"event_id": 99, "edep_MeV": 2.0},
                ]
            }
        ),
        encoding="utf-8",
    )

    _runner()._materialize_output_contract(
        output_dir=str(output_dir),
        executable_dir=str(executable_dir),
        job_id="job",
        events=1000,
        sim={"success": True},
    )

    rows = _read_rows(output_dir / "event_table.csv")
    assert len(rows) == 1000
    assert rows[0]["edep_MeV"] == "1"
    assert float(rows[0]["dose_Gy"]) > 0.0
    assert rows[99]["edep_MeV"] == "2"
    assert rows[100]["edep_MeV"] == "0"


@pytest.mark.asyncio
async def test_simulate_rejects_geant4_command_errors_even_with_zero_returncode(
    tmp_path: Path,
) -> None:
    runner = _runner()

    async def fake_run(cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        return (
            0,
            "",
            "***** COMMAND NOT FOUND </score/create/boxMesh siliconMesh> *****\n",
        )

    runner._run = fake_run  # type: ignore[method-assign]
    executable = tmp_path / "detector_sim"
    executable.write_text("", encoding="utf-8")

    result = await runner.simulate(str(executable), macro="run.mac")

    assert result["process_success"] is True
    assert result["success"] is False
    assert any("COMMAND NOT FOUND" in item for item in result["runtime_error_patterns"])


@pytest.mark.asyncio
async def test_smoke_test_uses_controlled_macro_with_requested_event_count(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    (project_dir / "macros").mkdir(parents=True)
    (project_dir / "macros" / "run.mac").write_text(
        "/run/initialize\n/run/beamOn 10\n",
        encoding="utf-8",
    )
    (project_dir / "CMakeLists.txt").write_text("find_package(Geant4 REQUIRED)\n", encoding="utf-8")
    runner = _runner()
    runner.geant4_available = True
    seen: dict[str, object] = {}

    async def fake_configure(source_dir: str, build_dir: str) -> dict[str, object]:
        return {"success": True}

    async def fake_build(build_dir: str) -> dict[str, object]:
        exe = Path(build_dir) / "sim"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        return {"success": True, "executable_path": str(exe)}

    async def fake_ctest(build_dir: str, output_dir: str) -> dict[str, object]:
        return {"success": True}

    async def fake_simulate(
        executable: str,
        macro: str | None = None,
        events: int = 100,
        threads: int = 1,
        output_dir: str | None = None,
        job_id: str = "unknown",
    ) -> dict[str, object]:
        seen["macro"] = macro
        seen["events"] = events
        assert macro is not None
        assert "/run/beamOn 1000" in Path(macro).read_text(encoding="utf-8")
        return {"success": True, "process_success": True, "log": "", "errors": ""}

    runner.configure = fake_configure  # type: ignore[method-assign]
    runner.build = fake_build  # type: ignore[method-assign]
    runner._run_ctest = fake_ctest  # type: ignore[method-assign]
    runner.simulate = fake_simulate  # type: ignore[method-assign]

    result = await runner.smoke_test(
        str(project_dir),
        output_dir=str(tmp_path / "out"),
        events=1000,
    )

    assert result["success"] is True
    assert seen["events"] == 1000
    assert Path(str(seen["macro"])).name == "radagent_self_check_1000.mac"


@pytest.mark.asyncio
async def test_smoke_test_exposes_full_runtime_diagnostics(tmp_path: Path) -> None:
    """Tool-facing smoke results must preserve the fatal Geant4 stderr."""
    project_dir = tmp_path / "geant4_project"
    project_dir.mkdir(parents=True)
    runner = _runner()
    runner.geant4_available = True
    g4_exception = (
        "*** G4Exception : GeomMgt0002\n"
        "Logical volume <WorldLV>\n"
        "does not have a valid material pointer.\n"
        "*** Fatal Exception *** core dump ***\n"
    )

    async def fake_configure(source_dir: str, build_dir: str) -> dict[str, object]:
        return {"success": True}

    async def fake_build(build_dir: str) -> dict[str, object]:
        exe = Path(build_dir) / "sim"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        return {"success": True, "executable_path": str(exe)}

    async def fake_ctest(build_dir: str, output_dir: str) -> dict[str, object]:
        return {"success": True}

    async def fake_simulate(
        executable: str,
        macro: str | None = None,
        events: int = 100,
        threads: int = 1,
        output_dir: str | None = None,
        job_id: str = "unknown",
    ) -> dict[str, object]:
        return {
            "success": False,
            "process_success": False,
            "returncode": 134,
            "log": "run started\n",
            "errors": g4_exception,
            "runtime_error_patterns": ["FatalException", "core dumped"],
        }

    runner.configure = fake_configure  # type: ignore[method-assign]
    runner.build = fake_build  # type: ignore[method-assign]
    runner._run_ctest = fake_ctest  # type: ignore[method-assign]
    runner.simulate = fake_simulate  # type: ignore[method-assign]

    result = await runner.smoke_test(
        str(project_dir),
        output_dir=str(tmp_path / "out"),
        events=5,
    )

    assert result["success"] is False
    assert result["run_success"] is False
    assert result["returncode"] == 134
    assert result["runtime_error_patterns"] == ["FatalException", "core dumped"]
    assert "GeomMgt0002" in result["run_errors"]
    assert "WorldLV" in result["run_errors"]
    assert "run started" in result["run_log"]


@pytest.mark.asyncio
async def test_smoke_test_treats_no_ctest_tests_as_skipped_success(tmp_path: Path) -> None:
    """Generated Geant4 projects often have no CTest tests; that must not trigger repair."""
    project_dir = tmp_path / "geant4_project"
    project_dir.mkdir(parents=True)
    runner = _runner()
    runner.geant4_available = True

    async def fake_configure(source_dir: str, build_dir: str) -> dict[str, object]:
        return {"success": True}

    async def fake_build(build_dir: str) -> dict[str, object]:
        exe = Path(build_dir) / "sim"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        return {"success": True, "executable_path": str(exe)}

    async def fake_run(command: str, cwd: str | None = None) -> tuple[int, str, str]:
        if command == "ctest --output-on-failure":
            return 1, "No tests were found!!!\n", ""
        return 0, "", ""

    async def fake_simulate(
        executable: str,
        macro: str | None = None,
        events: int = 100,
        threads: int = 1,
        output_dir: str | None = None,
        job_id: str = "unknown",
    ) -> dict[str, object]:
        return {"success": True, "process_success": True, "log": "run ok", "errors": ""}

    runner.configure = fake_configure  # type: ignore[method-assign]
    runner.build = fake_build  # type: ignore[method-assign]
    runner._run = fake_run  # type: ignore[method-assign]
    runner.simulate = fake_simulate  # type: ignore[method-assign]

    result = await runner.smoke_test(
        str(project_dir),
        output_dir=str(tmp_path / "out"),
        events=3,
    )

    assert result["success"] is True
    assert result["unit_test_result"]["success"] is True
    assert result["unit_test_result"]["skipped"] is True
