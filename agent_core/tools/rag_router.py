"""RAG router: determines which knowledge bases to query based on task spec.

Uses logical names (geant4, tcad, spice) exclusively — no legacy identifiers.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_VALID_DOMAINS = {"geant4", "tcad", "spice"}


class RAGRouter:
    """Route task specs to RAG source domains using logical names only."""

    def __init__(self, policy_path: str = "agent_core/policies/rag_policy.yaml") -> None:
        raw = yaml.safe_load(Path(policy_path).read_text())
        self._keywords: dict[str, list[str]] = raw["routing"]["keywords"]
        self._chain_keywords: dict[str, list[str]] = raw["routing"]["chain_keywords"]
        self._default_scope: str = raw["routing"]["default_route"]

    def route(self, task_spec: dict) -> dict:
        """Route RAG sources with required/optional distinction.

        Returns ``{"required": [...], "optional": [...], "all": [...]}``
        using logical names ("geant4", "tcad", "spice") only.
        """
        scope = task_spec.get("simulation_scope", [])
        text = " ".join(
            str(v) for v in task_spec.values() if isinstance(v, (str, list))
        )
        if isinstance(scope, str):
            scope = [scope]

        logical = self._resolve_logical_scope(scope, text)

        required: list[str] = []
        optional: list[str] = []

        scope_set = set(logical)
        if scope_set == {"geant4"}:
            required = ["geant4"]
            optional = ["tcad", "spice"]
        elif scope_set == {"tcad"}:
            required = ["tcad"]
            optional = []
        elif scope_set == {"spice"}:
            required = ["spice"]
            optional = []
        elif scope_set == {"geant4", "tcad"}:
            required = ["geant4", "tcad"]
            optional = ["spice"]
        elif scope_set == {"geant4", "tcad", "spice"}:
            required = ["geant4", "tcad", "spice"]
            optional = []
        else:
            required = [logical[0]] if logical else ["geant4"]
            optional = []

        all_sources = required + optional
        return {"required": required, "optional": optional, "all": all_sources}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_logical_scope(self, scope: list[str], text: str) -> list[str]:
        """Resolve scope + keyword detection to logical domain names."""
        if scope:
            valid = [s for s in scope if s in _VALID_DOMAINS]
            if valid:
                return valid

        # Try chain keywords
        for chain_name, keywords in self._chain_keywords.items():
            pattern = "|".join(re.escape(kw) for kw in keywords)
            if pattern and re.search(pattern, text, re.IGNORECASE):
                chain_map: dict[str, list[str]] = {
                    "g4_tcad": ["geant4", "tcad"],
                    "g4_tcad_spice": ["geant4", "tcad", "spice"],
                    "tcad_spice": ["tcad", "spice"],
                }
                return chain_map.get(chain_name, ["geant4"])

        # Individual domain keyword matching
        matched: list[str] = []
        for domain in self._keywords:
            if self._match_keywords(text, domain):
                matched.append(domain)
        if matched:
            return matched

        return [self._default_scope]

    def _match_keywords(self, text: str, domain: str) -> bool:
        pattern = "|".join(re.escape(kw) for kw in self._keywords.get(domain, []))
        return bool(re.search(pattern, text, re.IGNORECASE)) if pattern else False
