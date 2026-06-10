"""Architecture invariant tests for the subgraph refactoring.

These tests verify the structural constraints specified in the
refactoring requirements.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from agent_core.gates.base_gates import gate_name
from agent_core.workspace.paths import (
    ALL_STAGES,
    GEANT4_PROJECT_DIRNAME,
    STAGE_CODEGEN,
    STAGE_GATE_VALIDATION,
    STAGE_PATCH,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_CORE = PROJECT_ROOT / "agent_core"
README = PROJECT_ROOT / "README.md"
TESTS_ROOT = PROJECT_ROOT / "tests"


class TestNoOldMonolith:
    """Old monolithic graph_builder.py must NOT exist."""

    def test_no_old_graph_builder(self) -> None:
        assert not (AGENT_CORE / "graph" / "graph_builder.py").exists(), (
            "Old graph_builder.py must be deleted"
        )

    def test_no_old_graph_state(self) -> None:
        assert not (AGENT_CORE / "graph" / "state.py").exists(), "Old state.py must be deleted"

    def test_no_old_routes(self) -> None:
        assert not (AGENT_CORE / "graph" / "routes.py").exists(), "Old routes.py must be deleted"


class TestNoOldFanOut:
    """Old fan-out RAG retrieval must NOT exist."""

    def test_no_retrieve_g4_context(self) -> None:
        nodes_dir = AGENT_CORE / "nodes"
        if nodes_dir.exists():
            assert not (nodes_dir / "retrieve_g4_context.py").exists()
        # Should not exist anywhere
        for p in AGENT_CORE.rglob("retrieve_g4_context.py"):
            pytest.fail(f"Old file found: {p}")

    def test_no_retrieve_tcad_context(self) -> None:
        for p in AGENT_CORE.rglob("retrieve_tcad_context.py"):
            pytest.fail(f"Old file found: {p}")

    def test_no_retrieve_spice_context(self) -> None:
        for p in AGENT_CORE.rglob("retrieve_spice_context.py"):
            pytest.fail(f"Old file found: {p}")


class TestNoOldNaming:
    """Old compact RAG package names must NOT be used."""

    def test_no_geant4_rag_compact_references(self) -> None:
        """No Python file should reference the old Geant4 RAG module name."""
        old_name = "g4" + "rag"
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert old_name not in content, f"{old_name} found in {py_file}"

    def test_no_tcad_rag_compact_references(self) -> None:
        old_name = "tcad" + "rag"
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert old_name not in content, f"{old_name} found in {py_file}"

    def test_no_spice_rag_compact_references(self) -> None:
        old_name = "spice" + "rag"
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert old_name not in content, f"{old_name} found in {py_file}"


class TestNoRetiredCrossModuleRepair:
    """Retired cross-module repair files and graph nodes must not return."""

    def test_no_retired_cross_module_files(self) -> None:
        retired = [
            "global_" + "repair.py",
            "global_" + "llm_repair.py",
        ]
        for filename in retired:
            assert not (AGENT_CORE / "g4_codegen" / filename).exists()

    def test_no_retired_cross_module_symbols_in_agent_core(self) -> None:
        retired_tokens = [
            "global_" + "code_repair",
            "global_" + "llm_repair",
            "run_global_" + "code_repair",
            "run_global_" + "llm_repair",
        ]
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            for token in retired_tokens:
                assert token not in content, f"{token} found in {py_file}"


class TestNoRetiredCompatibilityModules:
    """Old bridge modules should not return once callers use canonical modules."""

    RETIRED_MODULE_FILES = [
        AGENT_CORE / "config" / "workspace.py",
        AGENT_CORE / "gates" / "nodes.py",
    ]
    RETIRED_IMPORTS = [
        "agent_core.config." + "workspace",
        "agent_core.gates." + "nodes",
    ]

    def test_no_retired_compatibility_module_files(self) -> None:
        for path in self.RETIRED_MODULE_FILES:
            assert not path.exists(), f"Retired compatibility module must be deleted: {path}"

    def test_no_retired_compatibility_imports(self) -> None:
        offenders = []
        roots = [AGENT_CORE, TESTS_ROOT, PROJECT_ROOT / "scripts"]
        for root in roots:
            for path in root.rglob("*.py"):
                if path == Path(__file__):
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
                for import_path in self.RETIRED_IMPORTS:
                    if import_path in content:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {import_path}")

        assert not offenders, "Retired compatibility imports found:\n" + "\n".join(offenders)


class TestSubgraphDirectoryStructure:
    """Verify subgraph directory structure exists."""

    REQUIRED_SUBGRAPHS = [
        "g4_modeling_graph.py",
        "g4_codegen_graph.py",
        "human_confirmation_graph.py",
    ]

    def test_subgraphs_dir_exists(self) -> None:
        assert (AGENT_CORE / "graph" / "subgraphs").is_dir()

    @pytest.mark.parametrize("subgraph_file", REQUIRED_SUBGRAPHS)
    def test_subgraph_file_exists(self, subgraph_file: str) -> None:
        path = AGENT_CORE / "graph" / "subgraphs" / subgraph_file
        assert path.exists(), f"Missing subgraph: {subgraph_file}"


class TestModuleDirectoryStructure:
    """Verify each subgraph has its own module directory."""

    REQUIRED_MODULES = [
        "context",
        "planning",
        "g4_modeling",
        "g4_codegen",
        "patching",
        "gates",
        "artifacts",
        "reports",
    ]

    @pytest.mark.parametrize("module", REQUIRED_MODULES)
    def test_module_dir_exists(self, module: str) -> None:
        mod_dir = AGENT_CORE / module
        assert mod_dir.is_dir(), f"Missing module dir: {module}"
        assert (mod_dir / "__init__.py").exists(), f"Missing __init__.py in {module}"


class TestArchitectureDocumentation:
    """README architecture section must cover top-level runtime packages."""

    IGNORED_TOP_LEVEL_DIRS = {"__pycache__"}

    def test_readme_documents_agent_core_top_level_packages(self) -> None:
        readme = README.read_text(encoding="utf-8")
        missing = []
        for path in sorted(AGENT_CORE.iterdir()):
            if not path.is_dir() or path.name in self.IGNORED_TOP_LEVEL_DIRS:
                continue
            if f"`agent_core.{path.name}`" not in readme and f"  {path.name}/" not in readme:
                missing.append(path.name)

        assert not missing, "README Architecture must document packages: " + ", ".join(missing)

    def test_readme_documents_agent_core_top_level_modules(self) -> None:
        readme = README.read_text(encoding="utf-8")
        required = ["main", "repl", "naming"]
        missing = [name for name in required if f"`agent_core.{name}`" not in readme]

        assert not missing, "README Architecture must document modules: " + ", ".join(missing)


class TestMainStateIsPathBased:
    """Main state must reference data by paths, not inline."""

    def test_no_inline_g4_model_ir(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        assert "g4_model_ir" not in annotations, (
            "g4_model_ir must NOT be inline in main state — use g4_model_ir_path"
        )
        assert "g4_model_ir_path" in annotations

    def test_no_inline_task_spec(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        assert "task_spec" not in annotations, "task_spec must NOT be inline — use task_spec_path"

    def test_no_tcad_spice_fields(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        for forbidden in [
            "tcad_context",
            "spice_context",
            "tcad_input_package",
            "spice_output_package",
        ]:
            assert forbidden not in annotations, f"Forbidden field: {forbidden}"


class TestNoSimulationWorkspaceInGit:
    """simulation_workspace/jobs must NOT be tracked in git."""

    def test_gitignore_blocks_jobs(self) -> None:
        gitignore = PROJECT_ROOT / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            # Must have some rule blocking simulation_workspace
            assert "simulation_workspace" in content, ".gitignore must block simulation_workspace"


class TestReviewArtifactsArchive:
    """Old review artifacts must be archived, not in latest."""

    def test_old_review_artifacts_archived(self) -> None:
        old_artifact_name = "mvp" + "1_e2e"
        old_artifact_top = PROJECT_ROOT / "review_artifacts" / old_artifact_name
        assert not old_artifact_top.exists(), (
            f"Old {old_artifact_name} artifacts must be moved to review_artifacts/archive/"
        )

    def test_archive_exists(self) -> None:
        archive = PROJECT_ROOT / "review_artifacts" / "archive"
        assert archive.is_dir(), "review_artifacts/archive/ must exist"


class TestNoDetachedBenchmarkSuite:
    """Unwired benchmark JSON suites should not live at repo root."""

    def test_no_detached_unwired_benchmarks(self) -> None:
        detached_suite = "benchmark" + "_suite"
        assert not (PROJECT_ROOT / detached_suite).exists(), (
            f"{detached_suite} was not connected to runtime/tests and must stay deleted"
        )


class TestReviewArtifactFixture:
    """Tracked review fixture must match current gate and confirmation design."""

    FIXTURE_ROOT = PROJECT_ROOT / "review_artifacts" / "g4_complex_model" / "latest"

    def test_fixture_gate_results_use_current_gate_ids_and_names(self) -> None:
        gate_path = self.FIXTURE_ROOT / "output" / "gate_results.json"
        gates = json.loads(gate_path.read_text(encoding="utf-8"))

        assert [gate["gate_id"] for gate in gates] == list(range(20))
        assert [gate["name"] for gate in gates] == [gate_name(gid) for gid in range(20)]
        assert gates[-1]["name"] == "G4-H Human Confirmation"

    def test_fixture_runtime_skips_are_explicitly_non_critical(self) -> None:
        gates = json.loads(
            (self.FIXTURE_ROOT / "output" / "gate_results.json").read_text(encoding="utf-8")
        )
        skipped = [gate for gate in gates if gate["status"] == "skipped"]

        assert skipped, "Fixture should not claim real runtime gates passed"
        assert all(gate.get("critical") is False for gate in skipped)

        manifest = json.loads(
            (self.FIXTURE_ROOT / "artifact_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["gate_summary"]["total_gates"] == 20
        assert manifest["gate_summary"]["skipped"] == len(skipped)
        assert manifest["validation_scope"] == "fixture_model_review"

    def test_fixture_includes_human_confirmation_artifacts(self) -> None:
        output_dir = self.FIXTURE_ROOT / "output"
        for filename in (
            "confirmation_record.json",
            "confirmed_model_plan.json",
            "human_confirmation_report.md",
        ):
            assert (output_dir / filename).is_file(), f"Missing {filename}"


class TestNoTrackedJobArtifacts:
    """No simulation_workspace/jobs should be in git tracking."""

    def test_no_tracked_jobs_dir(self) -> None:
        """simulation_workspace/ is fully gitignored."""
        gitignore = PROJECT_ROOT / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        # Must have a rule that blocks simulation_workspace
        assert "simulation_workspace/" in content, (
            ".gitignore must block simulation_workspace/ entirely"
        )


class TestWorkspaceStageNames:
    """Runtime code must use the current workspace stage naming scheme."""

    RETIRED_STAGE_NAMES = {
        "00_" + "request",
        "02_" + "task_spec",
        "03_" + "modeling",
        "05_" + "model_ir",
        "06_" + "codegen",
        "07_" + "patch",
        "08_" + "gate_validation",
        "08_" + "geant4",
        "09_" + "artifacts",
        "09_" + "validation",
        "10_" + "report",
    }

    def test_agent_core_does_not_reference_retired_stage_names(self) -> None:
        offenders = []
        for path in AGENT_CORE.rglob("*.py"):
            content = path.read_text(encoding="utf-8", errors="replace")
            for stage_name in self.RETIRED_STAGE_NAMES:
                if stage_name in content:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {stage_name}")

        assert not offenders, "Retired workspace stage names found:\n" + "\n".join(offenders)

    def test_acceptance_artifact_check_uses_stage_constants(self) -> None:
        source = (PROJECT_ROOT / "scripts" / "acceptance_check_artifacts.py").read_text(
            encoding="utf-8"
        )

        assert "STAGE_PATCH" in source
        assert "STAGE_CODEGEN" in source
        assert "STAGE_GATE_VALIDATION" in source
        for stage_name in (STAGE_PATCH, STAGE_CODEGEN, STAGE_GATE_VALIDATION):
            assert f'"{stage_name}"' not in source

    def test_workspace_stage_numbers_are_contiguous(self) -> None:
        numbered = [stage for stage in ALL_STAGES if stage[:2].isdigit()]
        prefixes = [int(stage[:2]) for stage in numbered]
        assert prefixes == list(range(len(numbered)))
        assert len(prefixes) == len(set(prefixes))

    def test_stage_names_are_centralized(self) -> None:
        allowed = {
            AGENT_CORE / "workspace" / "paths.py",
            AGENT_CORE / "workspace" / "__init__.py",
        }
        current_stage_names = {
            stage for stage in ALL_STAGES if len(stage) > 3 and stage[:2].isdigit()
        }
        offenders = []

        for root in (AGENT_CORE, PROJECT_ROOT / "scripts"):
            for py_file in root.rglob("*.py"):
                if py_file in allowed:
                    continue
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                        continue
                    for stage_name in current_stage_names:
                        if stage_name in node.value:
                            offenders.append(
                                f"{py_file.relative_to(PROJECT_ROOT)}:{node.lineno}: "
                                f"{stage_name}"
                            )

        assert not offenders, (
            "Stage directory names must be imported from workspace.paths:\n"
            + "\n".join(offenders)
        )

    def test_geant4_project_dir_is_not_a_numbered_stage(self) -> None:
        assert GEANT4_PROJECT_DIRNAME in {"geant4_project"}
        assert not GEANT4_PROJECT_DIRNAME[:2].isdigit()
        assert GEANT4_PROJECT_DIRNAME not in ALL_STAGES

    def test_pipeline_phase_order_is_centralized(self) -> None:
        from agent_core.app import PIPELINE_PHASES as APP_PIPELINE_PHASES
        from agent_core.pipeline import PIPELINE_PHASES
        from agent_core.repl import _PIPELINE_PHASES as REPL_PIPELINE_PHASES

        assert APP_PIPELINE_PHASES == PIPELINE_PHASES
        assert tuple(REPL_PIPELINE_PHASES) == PIPELINE_PHASES

    def test_completed_phase_index_uses_pipeline_length(self) -> None:
        source = (AGENT_CORE / "storage" / "repositories.py").read_text(encoding="utf-8")
        assert "current_phase_idx=" + "10" not in source
        assert "current_phase_idx=len(PIPELINE_PHASES)" in source

    def test_agent_core_does_not_create_geant4_project_at_job_root(self) -> None:
        offenders = []
        for path in AGENT_CORE.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if not isinstance(node, ast.BinOp | ast.JoinedStr):
                    continue
                source = ast.get_source_segment(content, node) or ""
                mentions_project = (
                    f'/ "{GEANT4_PROJECT_DIRNAME}"' in source
                    or "/ GEANT4_PROJECT_DIRNAME" in source
                )
                mentions_job_root = (
                    "job_dir" in source or "get_job_dir(" in source or "self.dir" in source
                )
                if mentions_project and mentions_job_root and "STAGE_PATCH" not in source:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {source.strip()}")

        assert not offenders, "Geant4 project root must live under STAGE_PATCH:\n" + "\n".join(
            offenders
        )


class TestModelConfigurationSurface:
    """User-facing model configuration is URL/key/model only."""

    def test_provider_env_switch_is_not_user_config(self) -> None:
        retired_env = "RADAGENT_MODEL_" + "PROVIDER"
        offenders = []
        roots = [
            AGENT_CORE,
            PROJECT_ROOT / "scripts",
            PROJECT_ROOT / "tests",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / ".env.example",
        ]

        for path in _iter_text_files(roots):
            if path == Path(__file__):
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            if retired_env in content:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        assert not offenders, "Retired model provider env config found:\n" + "\n".join(offenders)

    def test_frontend_model_config_does_not_expose_provider(self) -> None:
        from agent_core.app.schemas import ModelConfigUpdate, ModelTierConfig

        assert "provider" not in ModelConfigUpdate.model_fields
        assert "provider" not in ModelTierConfig.model_fields


class TestNoDetachedRuntimeModules:
    """Runtime modules must either be imported by code or be explicit entry points."""

    ROOTS = [
        PROJECT_ROOT / "agent_core",
        PROJECT_ROOT / "knowledge_base",
        PROJECT_ROOT / "scripts",
    ]
    LOCAL_TOP_LEVELS = {"agent_core", "knowledge_base", "scripts"}

    def test_no_non_entry_zero_in_degree_modules(self) -> None:
        modules = _collect_python_modules(self.ROOTS)
        incoming = _collect_incoming_import_edges(modules, self.LOCAL_TOP_LEVELS)

        detached = []
        for module_name, path in sorted(modules.items()):
            if path.name == "__init__.py":
                continue
            if incoming[module_name]:
                continue
            if _has_main_entrypoint(path):
                continue
            detached.append(f"{module_name} ({path.relative_to(PROJECT_ROOT)})")

        assert not detached, "Detached runtime modules found:\n" + "\n".join(detached)

    def test_runtime_modules_are_reachable_from_entry_points(self) -> None:
        modules = _collect_python_modules(self.ROOTS)
        edges = _collect_outgoing_import_edges(modules, self.LOCAL_TOP_LEVELS)
        entry_points = {
            module_name
            for module_name, path in modules.items()
            if module_name.startswith("scripts.")
            or path.name == "__main__.py"
            or _has_main_entrypoint(path)
        }
        entry_points.update(
            name
            for name in (
                "agent_core",
                "agent_core.tui.app",
                "knowledge_base",
                "knowledge_base.geant4",
                "knowledge_base.tcad",
            )
            if name in modules
        )

        reachable = _reachable_modules(entry_points, edges)
        unreachable = []
        for module_name, path in sorted(modules.items()):
            if path.name == "__init__.py":
                continue
            if module_name not in reachable:
                unreachable.append(f"{module_name} ({path.relative_to(PROJECT_ROOT)})")

        assert not unreachable, "Runtime modules unreachable from entry points:\n" + "\n".join(
            unreachable
        )


class TestPackageInitBoundaries:
    """Package initializers should stay as light public APIs."""

    PACKAGE_ROOTS = [AGENT_CORE, PROJECT_ROOT / "knowledge_base"]

    def test_package_inits_have_module_docstrings(self) -> None:
        offenders = []
        for root in self.PACKAGE_ROOTS:
            for path in root.rglob("__init__.py"):
                tree = ast.parse(path.read_text(encoding="utf-8") or "\n")
                if ast.get_docstring(tree):
                    continue
                rel_path = path.relative_to(PROJECT_ROOT)
                offenders.append(str(rel_path))

        assert not offenders, "__init__.py files need a package docstring:\n" + "\n".join(
            offenders
        )

    def test_package_inits_do_not_define_business_functions(self) -> None:
        offenders = []
        for root in self.PACKAGE_ROOTS:
            for path in root.rglob("__init__.py"):
                tree = ast.parse(path.read_text(encoding="utf-8") or "\n")
                functions = [
                    node.name
                    for node in tree.body
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                ]
                if functions:
                    rel_path = path.relative_to(PROJECT_ROOT)
                    offenders.append(f"{rel_path}: {', '.join(functions)}")

        assert not offenders, "Move __init__.py functions into explicit modules:\n" + "\n".join(
            offenders
        )

    def test_no_empty_leaf_packages(self) -> None:
        offenders = []
        for root in self.PACKAGE_ROOTS:
            for init_path in root.rglob("__init__.py"):
                package_dir = init_path.parent
                py_children = [
                    path for path in package_dir.glob("*.py") if path.name != "__init__.py"
                ]
                child_packages = [
                    path
                    for path in package_dir.iterdir()
                    if path.is_dir() and (path / "__init__.py").exists()
                ]
                if (
                    not py_children
                    and not child_packages
                    and not init_path.read_text(encoding="utf-8")
                ):
                    offenders.append(str(init_path.relative_to(PROJECT_ROOT)))

        assert not offenders, "Empty leaf packages found:\n" + "\n".join(offenders)


class TestNoCompatibilityTestWrappers:
    """Tests should live in their canonical package, not re-export old paths."""

    def test_no_test_reexport_wrappers(self) -> None:
        offenders = []
        for path in TESTS_ROOT.rglob("test_*.py"):
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            tree = ast.parse(content or "\n")
            body = [node for node in tree.body if not isinstance(node, ast.Expr)]
            if (
                len(body) == 1
                and isinstance(body[0], ast.ImportFrom)
                and body[0].module
                and body[0].module.startswith("tests.")
                and any(alias.name == "*" for alias in body[0].names)
            ):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        assert not offenders, "Test re-export wrappers found:\n" + "\n".join(offenders)


def _collect_python_modules(roots: list[Path]) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for root in roots:
        for path in root.rglob("*.py"):
            rel = path.with_suffix("").relative_to(PROJECT_ROOT)
            parts = rel.parts
            module_name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            modules[module_name] = path
    return modules


def _iter_text_files(roots: list[Path]) -> list[Path]:
    suffixes = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".mmd"}
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in suffixes:
                files.append(path)
    return files


def _collect_incoming_import_edges(
    modules: dict[str, Path],
    local_top_levels: set[str],
) -> dict[str, set[str]]:
    incoming: dict[str, set[str]] = {module_name: set() for module_name in modules}

    for source_module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in local_top_levels:
                        _add_import_edge(source_module, alias.name, modules, incoming)
            elif isinstance(node, ast.ImportFrom):
                target = _resolve_import_from_target(source_module, path, node)
                if target and target.split(".", 1)[0] in local_top_levels:
                    _add_import_edge(source_module, target, modules, incoming)
                    for alias in node.names:
                        if alias.name != "*":
                            _add_import_edge(
                                source_module,
                                f"{target}.{alias.name}",
                                modules,
                                incoming,
                            )

    return incoming


def _collect_outgoing_import_edges(
    modules: dict[str, Path],
    local_top_levels: set[str],
) -> dict[str, set[str]]:
    outgoing: dict[str, set[str]] = {module_name: set() for module_name in modules}

    for source_module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in local_top_levels:
                        target = _resolve_existing_module(alias.name, modules)
                        if target and target != source_module:
                            outgoing[source_module].add(target)
            elif isinstance(node, ast.ImportFrom):
                target = _resolve_import_from_target(source_module, path, node)
                if target and target.split(".", 1)[0] in local_top_levels:
                    resolved = _resolve_existing_module(target, modules)
                    if resolved and resolved != source_module:
                        outgoing[source_module].add(resolved)
                    for alias in node.names:
                        if alias.name != "*":
                            resolved = _resolve_existing_module(
                                f"{target}.{alias.name}",
                                modules,
                            )
                            if resolved and resolved != source_module:
                                outgoing[source_module].add(resolved)

    return outgoing


def _resolve_import_from_target(
    source_module: str,
    source_path: Path,
    node: ast.ImportFrom,
) -> str | None:
    if not node.level:
        return node.module

    parts = source_module.split(".")
    base = parts if source_path.name == "__init__.py" else parts[:-1]
    prefix_len = len(base) - node.level + 1
    if prefix_len < 0:
        return None
    resolved_parts = base[:prefix_len]
    if node.module:
        resolved_parts.extend(node.module.split("."))
    return ".".join(resolved_parts)


def _add_import_edge(
    source_module: str,
    target: str,
    modules: dict[str, Path],
    incoming: dict[str, set[str]],
) -> None:
    target_parts = target.split(".")
    for length in range(len(target_parts), 0, -1):
        candidate = ".".join(target_parts[:length])
        if candidate in modules and candidate != source_module:
            incoming[candidate].add(source_module)
            return


def _resolve_existing_module(target: str, modules: dict[str, Path]) -> str | None:
    target_parts = target.split(".")
    for length in range(len(target_parts), 0, -1):
        candidate = ".".join(target_parts[:length])
        if candidate in modules:
            return candidate
    return None


def _reachable_modules(
    entry_points: set[str],
    outgoing: dict[str, set[str]],
) -> set[str]:
    reachable: set[str] = set()
    stack = list(entry_points)
    while stack:
        module_name = stack.pop()
        if module_name in reachable:
            continue
        reachable.add(module_name)
        stack.extend(outgoing.get(module_name, set()) - reachable)
    return reachable


def _has_main_entrypoint(path: Path) -> bool:
    source = path.read_text(encoding="utf-8", errors="replace")
    return 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source
