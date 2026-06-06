"""No legacy names in codebase tests.

Scans the codebase for deprecated names that were renamed during cleanup.
Ensures g4rag, tcadrag, spicerag, and other legacy identifiers are gone.
Covers both lowercase (identifiers) and UPPERCASE (env vars) variants.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git_grep(pattern: str, pathspec: str = "") -> list[str]:
    """Run git grep and return matching lines (empty list if none)."""
    cmd = ["git", "grep", "-n", "-i", pattern]
    if pathspec:
        cmd.append("--")
        cmd.append(pathspec)
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _filter_deprecated_compat(matches: list[str]) -> list[str]:
    """Filter out lines that are explicitly marked as deprecated compat."""
    return [m for m in matches if "deprecated" not in m.lower()]


class TestNoLegacyRagNames:
    """Legacy RAG tool names must be removed from production code."""

    def test_no_g4rag_in_production_code(self):
        """'g4rag' should not appear in agent_core/ (except deprecated compat)."""
        matches = _git_grep("g4rag", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy 'g4rag' in agent_core/:\n" + "\n".join(real)
        )

    def test_no_tcadrag_in_production_code(self):
        """'tcadrag' should not appear in agent_core/."""
        matches = _git_grep("tcadrag", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy 'tcadrag' in agent_core/:\n" + "\n".join(real)
        )

    def test_no_spicerag_in_production_code(self):
        """'spicerag' should not appear in agent_core/."""
        matches = _git_grep("spicerag", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy 'spicerag' in agent_core/:\n" + "\n".join(real)
        )


class TestNoLegacyEnvVars:
    """Legacy UPPERCASE env var names should be gone from production code."""

    def test_no_g4rag_uppercase_in_production(self):
        """G4RAG_MCP_ENDPOINT etc. should not appear in agent_core/ (except deprecated compat)."""
        matches = _git_grep("G4RAG", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy G4RAG in agent_core/:\n" + "\n".join(real)
        )

    def test_no_tcadrage_uppercase_in_production(self):
        """TCADRAG_ENDPOINT etc. should not appear in agent_core/."""
        matches = _git_grep("TCADRAG", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy TCADRAG in agent_core/:\n" + "\n".join(real)
        )

    def test_no_spicerage_uppercase_in_production(self):
        """SPICERAG_ENDPOINT etc. should not appear in agent_core/."""
        matches = _git_grep("SPICERAG", "agent_core/")
        real = _filter_deprecated_compat(matches)
        assert len(real) == 0, (
            "Found legacy SPICERAG in agent_core/:\n" + "\n".join(real)
        )


class TestNoLegacyDecisionEnum:
    """Old decision enum values should not appear in production code."""

    def test_no_allow_with_warning_in_production(self):
        """'allow_with_warning' (old enum) should not be in agent_core/."""
        matches = _git_grep("allow_with_warning", "agent_core/")
        assert len(matches) == 0, (
            "Found legacy 'allow_with_warning' in agent_core/:\n"
            + "\n".join(matches)
        )

    def test_no_bare_allow_in_schemas(self):
        """Bare 'allow' (old enum) should not be in rag_context_pack.py."""
        matches = _git_grep('"allow"', "agent_core/schemas/rag_context_pack.py")
        real = [
            m for m in matches
            if '"allow"' in m and "allow_rag" not in m
        ]
        assert len(real) == 0, (
            "Found bare '\"allow\"' in rag_context_pack.py (should be 'allow_rag'):\n"
            + "\n".join(real)
        )

    def test_no_bare_block_in_decision_enum(self):
        """Bare 'block' should not be in rag_context_pack.py decision enum."""
        matches = _git_grep('"block"', "agent_core/schemas/rag_context_pack.py")
        real = [m for m in matches if '"block"' in m and "block_no_context" not in m]
        assert len(real) == 0, (
            "Found bare '\"block\"' in rag_context_pack.py (should be 'block_no_context'):\n"
            + "\n".join(real)
        )


class TestNoLegacyEnvEndpoints:
    """Old .env endpoint names should be removed."""

    def test_no_g4rag_endpoint_in_env_example(self):
        """G4RAG_ENDPOINT should not appear in .env.example."""
        content = (REPO_ROOT / ".env.example").read_text()
        assert "G4RAG_ENDPOINT" not in content, (
            "Found legacy G4RAG_ENDPOINT in .env.example"
        )

    def test_no_tcadrage_endpoint_in_env_example(self):
        """TCADRAG_ENDPOINT should not appear in .env.example."""
        content = (REPO_ROOT / ".env.example").read_text()
        assert "TCADRAG_ENDPOINT" not in content, (
            "Found legacy TCADRAG_ENDPOINT in .env.example"
        )
