"""RAG router: determines which knowledge bases to query based on task spec."""

import re
from pathlib import Path

import yaml

_SCOPE_MAP = {
    "geant4": "g4rag",
    "tcad": "tcadrag",
    "spice": "spicerag",
}

_CHAIN_SOURCES = {
    "g4_tcad": ["g4rag", "tcadrag"],
    "g4_tcad_spice": ["g4rag", "tcadrag", "spicerag"],
    "tcad_spice": ["tcadrag", "spicerag"],
}


class RAGRouter:
    def __init__(self, policy_path: str = "agent_core/policies/rag_policy.yaml"):
        raw = yaml.safe_load(Path(policy_path).read_text())
        self._keywords: dict[str, list[str]] = raw["routing"]["keywords"]
        self._chain_keywords: dict[str, list[str]] = raw["routing"]["chain_keywords"]
        self._default_scope: str = raw["routing"]["default_route"]

    def route(self, task_spec: dict) -> list[str]:
        scope = task_spec.get("simulation_scope", [])
        text = " ".join(
            str(v) for v in task_spec.values() if isinstance(v, (str, list))
        )
        if isinstance(scope, str):
            scope = [scope]

        # 1. explicit scope takes priority
        if scope:
            return self._scope_to_sources(scope)

        # 2. chain keywords produce combined sources
        chain = self._detect_chain(text)
        if chain:
            return chain

        # 3. individual domain keyword matching
        sources: list[str] = []
        for domain in self._keywords:
            if self._match_keywords(text, domain):
                sources.append(_SCOPE_MAP[domain])
        if sources:
            return sources

        # 4. fallback
        return self.get_fallback_sources()

    def _match_keywords(self, text: str, domain: str) -> bool:
        pattern = "|".join(re.escape(kw) for kw in self._keywords.get(domain, []))
        return bool(re.search(pattern, text, re.IGNORECASE)) if pattern else False

    def _detect_chain(self, text: str) -> list[str]:
        for chain_name, keywords in self._chain_keywords.items():
            pattern = "|".join(re.escape(kw) for kw in keywords)
            if pattern and re.search(pattern, text, re.IGNORECASE):
                return _CHAIN_SOURCES[chain_name]
        return []

    def _scope_to_sources(self, scope: list[str]) -> list[str]:
        mapped = [_SCOPE_MAP[s] for s in scope if s in _SCOPE_MAP]
        return mapped or self.get_fallback_sources()

    def route_with_priority(self, task_spec: dict) -> dict:
        """Route RAG sources with required/optional distinction.

        Returns ``{"required": [...], "optional": [...], "all": [...]}`` where
        *required* sources must return context to pass sufficiency, and
        *optional* sources are bonuses.  Logical names ("geant4", "tcad",
        "spice") are used — NOT the legacy RAG identifiers.
        """
        scope = task_spec.get("simulation_scope", [])
        text = " ".join(
            str(v) for v in task_spec.values() if isinstance(v, (str, list))
        )
        if isinstance(scope, str):
            scope = [scope]

        # Determine logical scope list (same logic as route, but keep names)
        logical = self._resolve_logical_scope(scope, text)

        required: list[str] = []
        optional: list[str] = []

        # Priority mapping
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
            # default fallback
            required = ["geant4"]
            optional = []

        all_sources = required + optional
        return {"required": required, "optional": optional, "all": all_sources}

    def _resolve_logical_scope(self, scope: list[str], text: str) -> list[str]:
        """Resolve scope + keyword detection to logical domain names."""
        if scope:
            return [s for s in scope if s in _SCOPE_MAP]

        # Try chain keywords
        for chain_name, keywords in self._chain_keywords.items():
            pattern = "|".join(re.escape(kw) for kw in keywords)
            if pattern and re.search(pattern, text, re.IGNORECASE):
                # Map chain source names back to logical names
                reverse = {v: k for k, v in _SCOPE_MAP.items()}
                return [reverse[s] for s in _CHAIN_SOURCES.get(chain_name, []) if s in reverse]

        # Individual domain keyword matching
        matched: list[str] = []
        for domain in self._keywords:
            if self._match_keywords(text, domain):
                matched.append(domain)
        if matched:
            return matched

        return [self._default_scope]

    def get_fallback_sources(self) -> list[str]:
        return [_SCOPE_MAP.get(self._default_scope, "g4rag")]
