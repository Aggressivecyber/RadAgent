"""Report generators for Human Confirmation Subgraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_confirmation_report(
    record: dict[str, Any],
    output_dir: Path,
) -> str:
    """Generate human_confirmation_report.md from confirmation record.

    Returns the path to the generated report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Human Confirmation Report",
        "",
        f"**Job ID**: {record.get('job_id', 'unknown')}",
        f"**Final Status**: {record.get('final_status', 'unknown')}",
        f"**Total Rounds**: {record.get('total_rounds', 0)}",
        "",
    ]

    # Confirmed fields
    confirmed = record.get("confirmed_fields", [])
    if confirmed:
        lines.append("## Confirmed Fields")
        for f in confirmed:
            lines.append(f"- ✅ {f}")
        lines.append("")

    # Edited fields
    edited = record.get("edited_fields", [])
    if edited:
        lines.append("## Edited Fields")
        for f in edited:
            lines.append(f"- ✏️ {f}")
        lines.append("")

    # Rejected fields
    rejected = record.get("rejected_fields", [])
    if rejected:
        lines.append("## Rejected Fields")
        for f in rejected:
            lines.append(f"- ❌ {f}")
        lines.append("")

    # Remaining unconfirmed
    remaining = record.get("remaining_unconfirmed_fields", [])
    if remaining:
        lines.append("## Remaining Unconfirmed Fields")
        for f in remaining:
            lines.append(f"- ⚠️ {f}")
        lines.append("")

    # History
    history = record.get("confirmation_history", [])
    if history:
        lines.append("## Confirmation History")
        for i, entry in enumerate(history, 1):
            decision = entry.get("user_decision", "unknown")
            round_id = entry.get("round_id", i)
            lines.append(f"### Round {round_id}")
            lines.append(f"- Decision: **{decision}**")
            edits = entry.get("edits", [])
            if edits:
                for e in edits:
                    lines.append(
                        f"  - Edit: {e.get('field_path', '?')} → {e.get('new_value', '?')}"
                    )
            lines.append("")

    if record.get("final_status") == "failed":
        lines.append("> ⚠️ **Human confirmation incomplete; formal codegen blocked.**")

    report_path = output_dir / "human_confirmation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)
