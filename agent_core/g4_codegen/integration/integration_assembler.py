"""Integration assembler — combines module outputs into proposed_patch."""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN


def assemble_proposed_patch(
    module_results: dict[str, dict[str, Any]],
    job_id: str,
) -> dict[str, Any]:
    """Assemble proposed_patch from generated module results.

    The final integration agent owns compile/runtime repair from real
    observations, so the assembler forwards every file produced by a
    generated/repaired coarse module.
    Output uses new_content field (never 'content').
    """
    changed_files: list[dict[str, Any]] = []
    included_count = 0
    failed_count = 0
    repair_input_count = 0
    agent_file_count = 0

    for module_name, result in module_results.items():
        generated_files = result.get("generated_files", [])
        has_files = bool(generated_files)
        if result.get("status") not in {"generated", "repaired"}:
            failed_count += 1
            if not has_files:
                continue
            repair_input_count += 1
        else:
            included_count += 1

        for f in generated_files:
            raw_path = f["path"]
            # Security: reject path traversal
            if ".." in raw_path or raw_path.startswith("/"):
                continue
            # Strip any leading directory prefix so path is relative to geant4_project
            clean_path = raw_path.lstrip("/")
            if clean_path.startswith("geant4_project/"):
                clean_path = clean_path[len("geant4_project/") :]
            elif clean_path.startswith("geant4_project"):
                clean_path = clean_path[len("geant4_project") :].lstrip("/")

            changed_files.append(
                {
                    "path": clean_path,
                    "operation": f.get("operation", "create"),
                    "new_content": f["new_content"],
                    "zone": "green",
                    "generated_by": f.get("generated_by", f"{module_name}_module_agent"),
                    "module_name": f.get("module_name", module_name),
                    "rationale": f.get("rationale", ""),
                    "dependencies": f.get("dependencies", []),
                    "satisfies": f.get("satisfies", []),
                    "risk_notes": f.get("risk_notes", []),
                    "used_references": f.get("used_references", []),
                }
            )
            agent_file_count += 1

    # Force the canonical CMakeLists.txt (Geant4 B1 template that file(GLOB)s
    # every src/*.cc + include/*.hh). CMake is formulaic and the model
    # reinventing it per run was a recurring source of build failures; the
    # glob template needs no per-project editing, so the canonical version
    # always wins regardless of what the runtime_app agent emitted.
    from agent_core.g4_codegen.cmake_template import CMAKE_PATH, RADAGENT_CMAKE_TEMPLATE

    changed_files = [c for c in changed_files if c.get("path") != CMAKE_PATH]
    changed_files.append(
        {
            "path": CMAKE_PATH,
            "operation": "create_or_replace",
            "new_content": RADAGENT_CMAKE_TEMPLATE,
            "zone": "green",
            "generated_by": "canonical_cmake_template",
            "module_name": "runtime_app",
            "rationale": "Fixed B1-derived CMake (ui_all vis_all + file(GLOB sources))",
            "dependencies": [],
            "satisfies": [],
            "risk_notes": [],
            "used_references": [],
        }
    )
    interface_audit = _audit_generated_interfaces(changed_files)

    patch = {
        "patch_id": f"patch_{job_id}_g4_codegen",
        "job_id": job_id,
        "description": "Agent-generated Geant4 project files from module-level codegen",
        "change_type": "create_or_replace",
        "risk_level": "medium",
        "patch_type": "json_file_replacement",
        "changed_files": changed_files,
        "test_plan": [
            "Verify all generated files compile with Geant4 toolchain",
            "Run dry-run simulation to confirm geometry/material setup",
        ],
        "expected_outputs": [
            "All files written to geant4_project directory",
            "No compilation errors in generated C++ code",
        ],
        "metadata": {
            "source": "g4_codegen_agent_modules",
            "module_agent_count": len(module_results),
            "included_module_count": included_count,
            "passed_module_count": included_count,
            "failed_module_count": failed_count,
            "repair_input_module_count": repair_input_count,
            "agent_authored_file_count": agent_file_count,
            "interface_audit": interface_audit,
        },
    }

    # Persist
    from agent_core.workspace.io import get_job_dir

    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)

    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text(json.dumps(patch, indent=2, ensure_ascii=False))

    summary_path = codegen_dir / "proposed_patch_summary.json"
    summary = {
        "patch_type": patch["patch_type"],
        "total_files": len(changed_files),
        "metadata": patch["metadata"],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    return patch


def _audit_generated_interfaces(changed_files: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect obvious cross-file C++ API mismatches before global repair.

    This is intentionally a shallow textual audit. It catches high-signal
    mistakes produced by separate module agents, such as calling a method that
    is absent from the generated header whose class type is visible locally.
    """
    class_methods: dict[str, set[str]] = {}
    class_headers: dict[str, str] = {}
    constructor_arities: dict[str, set[int]] = {}
    for entry in changed_files:
        path = str(entry.get("path") or "")
        content = str(entry.get("new_content") or "")
        if not path.startswith("include/") or not content:
            continue
        class_interfaces = _extract_public_interface_by_class(content)
        for class_name, interface in class_interfaces.items():
            methods = set(interface.get("methods", set()))
            class_methods.setdefault(class_name, set()).update(methods)
            arities = set(interface.get("constructor_arities", set()))
            if arities:
                constructor_arities.setdefault(class_name, set()).update(arities)
            class_headers.setdefault(class_name, path)

    issues: list[dict[str, Any]] = []
    for entry in changed_files:
        path = str(entry.get("path") or "")
        content = str(entry.get("new_content") or "")
        if not content or not (path.startswith("src/") or path == "main.cc"):
            continue
        variable_types = _extract_variable_types(content, class_methods.keys())
        for match in re.finditer(r"\b(?P<var>[A-Za-z_]\w*)\s*->\s*(?P<method>[A-Za-z_]\w*)\s*\(", content):
            var_name = match.group("var")
            method_name = match.group("method")
            class_name = variable_types.get(var_name)
            if not class_name or class_name not in class_methods:
                continue
            if method_name in class_methods[class_name]:
                continue
            line = content.count("\n", 0, match.start()) + 1
            issues.append(
                {
                    "kind": "unknown_method",
                    "path": path,
                    "line": line,
                    "class_name": class_name,
                    "variable": var_name,
                    "method": method_name,
                    "header_path": class_headers.get(class_name, ""),
                    "available_methods": sorted(class_methods[class_name])[:30],
                    "message": (
                        f"{path}:{line}: {class_name} has no public method "
                        f"{method_name}() in generated header "
                        f"{class_headers.get(class_name, 'unknown header')}."
                    ),
                }
            )
        for match in re.finditer(
            r"\bnew\s+(?P<class>[A-Za-z_]\w*)\s*\((?P<args>[^;{}()]*)\)",
            content,
        ):
            class_name = match.group("class")
            if class_name not in constructor_arities:
                continue
            actual_count = _argument_count(match.group("args"))
            allowed_counts = constructor_arities[class_name]
            if actual_count in allowed_counts:
                continue
            line = content.count("\n", 0, match.start()) + 1
            issues.append(
                {
                    "kind": "constructor_arity_mismatch",
                    "path": path,
                    "line": line,
                    "class_name": class_name,
                    "actual_arg_count": actual_count,
                    "allowed_arg_counts": sorted(allowed_counts),
                    "header_path": class_headers.get(class_name, ""),
                    "message": (
                        f"{path}:{line}: new {class_name}(...) passes {actual_count} "
                        f"arguments, but generated header "
                        f"{class_headers.get(class_name, 'unknown header')} declares "
                        f"constructor arities {sorted(allowed_counts)}."
                    ),
                }
            )

    return {
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "issues": issues[:80],
        "repair_hints": _interface_repair_hints(issues),
    }


def _extract_public_interface_by_class(content: str) -> dict[str, dict[str, set[int] | set[str]]]:
    cleaned = _strip_cpp_comments(content)
    classes: dict[str, dict[str, set[int] | set[str]]] = {}
    for class_match in re.finditer(r"\bclass\s+(?P<name>[A-Za-z_]\w*)[^{;]*\{", cleaned):
        class_name = class_match.group("name")
        body_start = class_match.end()
        body_end = _matching_class_body_end(cleaned, body_start - 1)
        if body_end <= body_start:
            continue
        body = cleaned[body_start:body_end]
        methods: set[str] = set()
        constructor_arities: set[int] = set()
        for public_block in re.findall(
            r"\bpublic:\s*(.*?)(?=\bprivate:|\bprotected:|$)",
            body,
            flags=re.DOTALL,
        ):
            for declaration in _split_declarations(public_block):
                if "(" not in declaration or ")" not in declaration:
                    continue
                method_name = _method_name_from_declaration(declaration)
                if not method_name:
                    continue
                if method_name == class_name:
                    constructor_arities.add(_argument_count(_declaration_args(declaration)))
                    continue
                if method_name.lstrip("~") == class_name:
                    continue
                methods.add(method_name)
        classes[class_name] = {
            "methods": methods,
            "constructor_arities": constructor_arities,
        }
    return classes


def _matching_class_body_end(content: str, open_brace_index: int) -> int:
    depth = 0
    for index in range(open_brace_index, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_declarations(block: str) -> list[str]:
    declarations: list[str] = []
    current: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        current.append(line)
        if ";" not in line:
            continue
        joined = " ".join(current)
        declarations.append(joined.split(";", 1)[0].strip())
        current = []
    return declarations


def _method_name_from_declaration(declaration: str) -> str:
    before_args = declaration.split("(", 1)[0].strip()
    if not before_args or "operator" in before_args:
        return ""
    return before_args.split()[-1].strip("*&")


def _declaration_args(declaration: str) -> str:
    if "(" not in declaration or ")" not in declaration:
        return ""
    return declaration.split("(", 1)[1].rsplit(")", 1)[0]


def _argument_count(args: str) -> int:
    text = str(args or "").strip()
    if not text or text == "void":
        return 0
    depth = 0
    count = 1
    for char in text:
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            count += 1
    return count


def _extract_variable_types(content: str, class_names: Any) -> dict[str, str]:
    known_classes = [re.escape(str(name)) for name in class_names if str(name)]
    if not known_classes:
        return {}
    class_pattern = "|".join(sorted(known_classes, key=len, reverse=True))
    pattern = re.compile(
        rf"\b(?P<class>{class_pattern})\s*(?:\*|&)?\s+(?P<name>[A-Za-z_]\w*)\b"
    )
    variables: dict[str, str] = {}
    for match in pattern.finditer(_strip_cpp_comments(content)):
        variables[match.group("name")] = match.group("class")
    return variables


def _strip_cpp_comments(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"//.*", "", content)


def _interface_repair_hints(issues: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for issue in issues[:20]:
        if issue.get("kind") == "constructor_arity_mismatch":
            hint = (
                f"Align {issue.get('path')} with {issue.get('header_path')}: "
                f"new {issue.get('class_name')}(...) passes "
                f"{issue.get('actual_arg_count')} arguments but the generated "
                f"header declares arities {issue.get('allowed_arg_counts')}. "
                "Read the constructor signature and update the call or the "
                "declaration/definition together."
            )
        else:
            hint = (
                f"Align {issue.get('path')} with {issue.get('header_path')}: "
                f"{issue.get('class_name')} does not declare "
                f"{issue.get('method')}(). Read the header and replace the call "
                "with an existing method or add a matching declaration/definition."
            )
        if hint in seen:
            continue
        seen.add(hint)
        hints.append(hint)
    return hints
