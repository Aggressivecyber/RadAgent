"""RAG context pack schema for simulation pipeline knowledge retrieval.

Decision model: allow_rag / needs_web / block_no_context.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RetrievedContext(BaseModel):
    """Structured output from RAG queries against domain knowledge bases."""

    manual_snippets: list[dict] = Field(
        default_factory=list,
        description="Manual excerpts: text, source, page",
    )
    example_code: list[dict] = Field(
        default_factory=list,
        description="Code examples: code, language, source, description",
    )
    data_contracts: list[dict] = Field(
        default_factory=list,
        description="I/O contracts: contract_name, schema, description",
    )
    error_cases: list[dict] = Field(
        default_factory=list,
        description="Known errors: error, solution, source",
    )
    benchmark_cases: list[dict] = Field(
        default_factory=list,
        description="Benchmarks: name, config, expected_results",
    )


class SufficiencyReport(BaseModel):
    """Assessment of whether retrieved context is adequate for the task."""

    score: float = Field(ge=0.0, le=1.0)
    missing_items: list[str] = Field(default_factory=list)
    decision: Literal["allow_rag", "needs_web", "block_no_context"]
    has_manual: bool
    has_examples: bool
    has_contracts: bool


class RAGContextPack(BaseModel):
    """Complete RAG context bundle for a pipeline stage execution."""

    job_id: str
    target_module: Literal["geant4", "tcad", "spice", "mapper", "validator"]
    retrieved_context: RetrievedContext
    sufficiency: SufficiencyReport
    query_used: str
    sources_queried: list[str] = Field(default_factory=list)


def compute_sufficiency(context: RetrievedContext) -> SufficiencyReport:
    """Score retrieved context and produce a sufficiency decision.

    Tri-state model:
      - allow_rag:         score >= 0.90, all categories present
      - needs_web:         score >= 0.60 but < 0.90
      - block_no_context:  score < 0.60
    """
    has_manual = len(context.manual_snippets) > 0
    has_examples = len(context.example_code) > 0
    has_contracts = len(context.data_contracts) > 0
    no_errors = len(context.error_cases) == 0
    has_benchmarks = len(context.benchmark_cases) > 0

    score = (
        0.30 * has_manual
        + 0.25 * has_examples
        + 0.20 * has_contracts
        + 0.15 * no_errors
        + 0.10 * has_benchmarks
    )

    missing: list[str] = []
    if not has_manual:
        missing.append("manual_snippets")
    if not has_examples:
        missing.append("example_code")
    if not has_contracts:
        missing.append("data_contracts")
    if not has_benchmarks:
        missing.append("benchmark_cases")

    if score >= 0.90:
        decision: Literal["allow_rag", "needs_web", "block_no_context"] = "allow_rag"
    elif score >= 0.60:
        decision = "needs_web"
    else:
        decision = "block_no_context"

    return SufficiencyReport(
        score=score,
        missing_items=missing,
        decision=decision,
        has_manual=has_manual,
        has_examples=has_examples,
        has_contracts=has_contracts,
    )
