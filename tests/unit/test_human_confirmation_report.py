"""Tests for human confirmation report generation."""

import json
from pathlib import Path

from agent_core.human_confirmation.reports import generate_confirmation_report


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_confirmation_report_reviews_simulation_plan(tmp_path):
    """Report summarizes proposal, confirmation record, and confirmed plan."""
    proposal = {
        "schema_version": "proposed_model_completion_v1",
        "job_id": "job-1",
        "source_query": "Simulate a 150 MeV proton beam in a water tank.",
        "domain_profile": "geant4",
        "proposed_components": [
            {
                "component_id": "water_tank",
                "component_type": "box",
                "material_id": "G4_WATER",
                "geometry": {"x": 10.0, "y": 10.0, "z": 10.0},
                "placement": {"position": [0, 0, 0]},
                "roles": ["target", "scoring_volume"],
                "parameters": [
                    {
                        "field_path": "components.water_tank.material_id",
                        "proposed_value": "G4_WATER",
                        "source_type": "user",
                        "confidence": 1.0,
                        "reason": "User specified water.",
                        "requires_confirmation": False,
                    }
                ],
            }
        ],
        "proposed_sources": [
            {
                "field_path": "sources.primary.energy",
                "proposed_value": "150 MeV",
                "unit": "MeV",
                "source_type": "rag",
                "confidence": 0.8,
                "reason": "Retrieved from treatment beam note.",
                "requires_confirmation": True,
            },
            {
                "field_path": "sources.primary.particle_type",
                "proposed_value": "proton",
                "source_type": "user",
                "confidence": 1.0,
                "reason": "User requested protons.",
                "requires_confirmation": False,
            },
        ],
        "proposed_scoring": [
            {
                "field_path": "scoring.dose.scoring_type",
                "proposed_value": "dose",
                "source_type": "default",
                "confidence": 0.6,
                "reason": "Default dose scoring.",
                "requires_confirmation": True,
            }
        ],
        "assumptions": ["Water tank is centered at the world origin."],
        "missing_information": ["Beam spot size was not specified."],
    }
    confirmed_plan = {
        "schema_version": "confirmed_model_plan_v1",
        "job_id": "job-1",
        "source_query": proposal["source_query"],
        "domain_profile": "geant4",
        "components": [],
        "sources": [],
        "scoring": [],
        "assumptions_confirmed": True,
        "confirmation_status": "edited",
    }
    record = {
        "schema_version": "confirmation_record_v1",
        "job_id": "job-1",
        "total_rounds": 1,
        "final_status": "edited",
        "confirmed_fields": [
            "components.water_tank.material_id",
            "sources.primary.particle_type",
            "scoring.dose.scoring_type",
        ],
        "edited_fields": ["sources.primary.energy"],
        "rejected_fields": [],
        "remaining_unconfirmed_fields": [],
        "unconfirmed_assumptions_count": 0,
        "confirmation_history": [
            {
                "round_id": 1,
                "user_decision": "edit",
                "edits": [
                    {
                        "field_path": "sources.primary.energy",
                        "new_value": "200 MeV",
                        "unit": "MeV",
                    }
                ],
                "user_notes": "Use the higher commissioned beam energy.",
            }
        ],
        "confirmed_model_plan_path": str(tmp_path / "confirmed_model_plan.json"),
    }

    _write_json(tmp_path / "proposed_model_completion.json", proposal)
    _write_json(tmp_path / "confirmed_model_plan.json", confirmed_plan)

    report_path = Path(generate_confirmation_report(record, tmp_path))
    report = report_path.read_text(encoding="utf-8")

    assert report_path.name == "human_confirmation_report.md"
    assert "## Task Summary" in report
    assert "## Object, Components, Materials, Sources, Scoring" in report
    assert "## Key Parameter Table" in report
    assert "## Assumptions and Risks" in report
    assert "## Required User Actions" in report
    assert "## Confirmation History" in report
    assert "## Codegen Readiness" in report
    assert "Simulate a 150 MeV proton beam in a water tank." in report
    assert "water_tank (box)" in report
    assert (
        "| sources.primary.energy | 200 MeV | MeV | rag: Retrieved from treatment beam note. "
        "| 0.80 | edited by user |"
    ) in report
    assert "Water tank is centered at the world origin." in report
    assert "Beam spot size was not specified." in report
    assert "READY - code generation can proceed" in report
    assert "No additional user action is required before code generation." in report


def test_confirmation_report_blocks_without_confirmed_plan(tmp_path):
    """Backward-compatible records still produce readable blocked reports."""
    record = {
        "schema_version": "confirmation_record_v1",
        "job_id": "job-2",
        "total_rounds": 1,
        "final_status": "approved",
        "confirmed_fields": ["sources.primary.energy"],
        "edited_fields": [],
        "rejected_fields": [],
        "remaining_unconfirmed_fields": [],
        "unconfirmed_assumptions_count": 0,
        "confirmation_history": [
            {
                "round_id": 1,
                "user_decision": "approve",
                "edits": [],
                "user_notes": "Approved.",
            }
        ],
        "confirmed_model_plan_path": None,
    }

    report_path = Path(generate_confirmation_report(record, tmp_path))
    report = report_path.read_text(encoding="utf-8")

    assert "No source query recorded." in report
    assert "| No key parameters available | n/a | n/a | n/a | n/a | unavailable |" in report
    assert "BLOCKED - confirmed model plan missing" in report
    assert "The confirmation record is complete but confirmed_model_plan.json is missing." in report
    assert "Complete human confirmation before code generation." in report
