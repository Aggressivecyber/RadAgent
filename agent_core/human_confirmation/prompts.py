"""Prompt templates for Human Confirmation Subgraph."""


def build_confirmation_summary(
    components: list[dict],
    sources: list[dict],
    scoring: list[dict],
    assumptions: list[str],
    missing: list[str],
) -> str:
    """Build human-readable confirmation summary for user."""
    sections = []

    # Geometry section
    if components:
        lines = ["一、几何结构"]
        for c in components:
            cid = c.get("component_id", "?")
            mat = c.get("material_id", "TBD")
            geom = c.get("geometry", {})
            dims = " × ".join(
                f"{geom.get(k, '?')}" for k in ("x", "y", "z") if k in geom
            )
            if not dims:
                dims = geom.get("dimensions", "?")
            lines.append(f"- {cid}: {mat}, {dims}")
        sections.append("\n".join(lines))

    # Source section
    if sources:
        lines = ["二、源项"]
        for s in sources:
            particle = s.get("particle_type", s.get("proposed_value", "?"))
            energy = s.get("energy", s.get("unit", ""))
            direction = s.get("direction", "")
            lines.append(f"- {particle}, {energy}, {direction}")
        sections.append("\n".join(lines))

    # Scoring section
    if scoring:
        lines = ["三、输出"]
        for sc in scoring:
            sid = sc.get("scoring_id", sc.get("field_path", "?"))
            stype = sc.get("scoring_type", "")
            lines.append(f"- {sid} {stype}")
        sections.append("\n".join(lines))

    # Assumptions section
    if assumptions:
        lines = ["四、AI 假设（需确认）"]
        for i, a in enumerate(assumptions, 1):
            lines.append(f"{i}. {a}")
        sections.append("\n".join(lines))

    # Missing info
    if missing:
        lines = ["五、缺失信息"]
        for m in missing:
            lines.append(f"- {m}")
        sections.append("\n".join(lines))

    header = "我根据你的需求和检索资料，补全了以下建模方案。请确认：\n"
    return header + "\n\n".join(sections)


def build_question_text(question: dict) -> str:
    """Build a single question for user."""
    qid = question.get("question_id", "?")
    text = question.get("question", "")
    proposed = question.get("proposed_value")
    unit = question.get("unit", "")

    if proposed is not None:
        return f"{qid}. {text}（提议值：{proposed}{f' {unit}' if unit else ''}）"
    return f"{qid}. {text}"


CONFIRMATION_ROUND_LIMIT = 3
MAX_QUESTIONS_PER_ROUND = 8

# Priority ordering for question generation
QUESTION_PRIORITY = [
    "source",      # particle / energy / direction
    "material",    # key materials
    "dimension",   # key dimensions
    "placement",   # layer relationships
    "scoring",     # sensitive region
    "output",      # scoring/output
    "voxel",       # voxel size
    "other",       # other assumptions
]
