"""Source module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_source_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for source module."""
    result = run_hard_gate_checks(
        module_name="source",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=["G4PVPlacement", "G4VSensitiveDetector"],
    )
    checks = list(result.checks)
    errors = list(result.errors)

    for file_entry in generated_files:
        content = file_entry.new_content
        if "SetParticlePosition" in content and "*cm" in content:
            checks.append(
                {
                    "check": "source_position_uses_global_length_unit",
                    "status": "fail",
                    "message": "Source position must use global length unit mm, not cm",
                }
            )
            errors.append(f"{file_entry.path}: source position must use mm, not cm")

        if file_entry.path == "src/PrimaryGeneratorAction.cc":
            generate_primaries = re.search(
                r"void\s+PrimaryGeneratorAction::GeneratePrimaries\s*"
                r"\(\s*G4Event\s*\*\s*(?P<param>[^)]*)\)\s*"
                r"\{(?P<body>.*?)\n\}",
                content,
                re.DOTALL,
            )
            if generate_primaries:
                param = generate_primaries.group("param").strip()
                body = generate_primaries.group("body")
                uses_event = bool(re.search(r"\bevent\b", body))
                names_event = bool(re.search(r"\bevent\b", param))
                comments_out_event = "/*event*/" in param or "/* event */" in param
                if uses_event and (not names_event or comments_out_event):
                    checks.append(
                        {
                            "check": "source_generate_primaries_names_event_parameter",
                            "status": "fail",
                            "message": (
                                "GeneratePrimaries must define G4Event* event when the "
                                "function body passes event to GeneratePrimaryVertex"
                            ),
                        }
                    )
                    errors.append(
                        f"{file_entry.path}: GeneratePrimaries must use "
                        "G4Event* event, not an unnamed or commented-out parameter"
                    )
            elif "GeneratePrimaries" in content:
                checks.append(
                    {
                        "check": "source_generate_primaries_signature_parseable",
                        "status": "fail",
                        "message": "GeneratePrimaries definition must be parseable",
                    }
                )
                errors.append(
                    f"{file_entry.path}: GeneratePrimaries definition must be parseable"
                )

    return ModuleGateResult(
        module_name="source",
        gate_type="hard",
        status="fail" if errors else result.status,
        checks=checks,
        errors=errors,
        warnings=list(result.warnings),
    )
