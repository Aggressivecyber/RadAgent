"""Redaction helpers for structured observability events."""

from __future__ import annotations

import hashlib
import re
from typing import Any

SECRET_KEY_RE = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.I)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")
KEY_VALUE_RE = re.compile(r"([?&](?:key|api_key|token|access_token)=)[^&\s]+", re.I)


def sanitize(value: Any, *, max_string: int = 1000) -> Any:
    """Return a JSON-safe, secret-redacted representation."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = sanitize(item, max_string=max_string)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item, max_string=max_string) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item, max_string=max_string) for item in value]
    if isinstance(value, str):
        text = BEARER_RE.sub("Bearer <redacted>", value)
        text = KEY_VALUE_RE.sub(r"\1<redacted>", text)
        if len(text) > max_string:
            digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            return {
                "preview": text[:max_string],
                "truncated": True,
                "sha256": digest,
                "byte_count": len(text.encode("utf-8", errors="ignore")),
            }
        return text
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


def artifact_ref(path: str, *, content: str | None = None) -> dict[str, Any]:
    """Build a small artifact reference without inlining large content."""
    ref: dict[str, Any] = {"path": path}
    if content is not None:
        encoded = content.encode("utf-8", errors="ignore")
        ref.update(
            {
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "byte_count": len(encoded),
                "preview": content[:300],
            }
        )
    return ref
