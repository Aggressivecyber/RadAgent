"""Job ID helpers.

Generated job IDs avoid semantic title suffixes so workspace directory names
remain compact and predictable.

Job ID format: ``job_{uuid8}__{YYYYMMDD_HHMMSS}``
Example: ``job_a1b2c3d4__20260611_150405``
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

_MAX_TITLE_LEN = 60

_SYSTEM_PROMPT = (
    "You are a job title generator. "
    "Given a user's simulation request, produce a short title in "
    "snake_case using 3-6 English words. "
    "Output ONLY the snake_case title, nothing else. "
    "Do not include any explanation, punctuation other than underscores, "
    "or line breaks."
)


def sanitize_title(text: str) -> str:
    """Convert free-form text to a filesystem-safe snake_case slug.

    Steps:
      1. Strip leading/trailing whitespace.
      2. Lowercase.
      3. Replace any character that is not ``a-z``, ``0-9``, or ``_``
         with an underscore.
      4. Collapse consecutive underscores into one.
      5. Strip leading/trailing underscores.
      6. Truncate to ``_MAX_TITLE_LEN`` characters.

    Args:
        text: Raw text (typically LLM output or user query).

    Returns:
        A sanitized slug suitable for use in file paths.
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_]", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    return text[:_MAX_TITLE_LEN]


async def generate_job_title(user_query: str) -> str:
    """Call model gateway (lite tier) to summarize *user_query* into a short title slug.

    Falls back to a simple slug derived from the first 3 English words
    if the model call fails for any reason.

    Args:
        user_query: The user's natural language simulation request.

    Returns:
        A sanitized title slug (possibly empty if no English words found).
    """
    title = await _call_model_gateway(user_query)
    if title:
        return sanitize_title(title)

    # Fallback: extract first 3 English words from user query
    return _fallback_slug(user_query)


async def _call_model_gateway(user_query: str) -> str:
    """Call the model gateway (lite tier) and return the raw title string.

    Returns an empty string on any failure.
    """
    try:
        from agent_core.models.gateway import get_model_gateway
        from agent_core.models.schemas import ModelTask, ModelTier

        gateway = get_model_gateway()
        result = await gateway.call(
            task=ModelTask.SIMPLE_EXTRACTION,
            tier=ModelTier.LITE,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_query,
            temperature=0.0,
            max_tokens=32,
        )

        if result.error:
            return ""

        return result.content.strip()
    except Exception:
        return ""


def _fallback_slug(user_query: str) -> str:
    """Generate a slug from the first 3 English words in *user_query*.

    Extracts ASCII alphabetic words, takes up to 3, joins with
    underscores, and sanitizes the result.
    """
    words = re.findall(r"[a-zA-Z]{2,}", user_query)
    slug = "_".join(words[:3])
    return sanitize_title(slug)


async def build_job_id(base_id: str, user_query: str) -> str:
    """Build a complete job ID with a creation-time suffix.

    If *base_id* is non-empty (user provided via ``--job-id``), it is
    returned unchanged. Otherwise a new UUID-based ID is generated with a
    timestamp suffix using local 24-hour time. *user_query* is accepted for
    backward compatibility with existing call sites and is not used for
    semantic directory naming.

    Args:
        base_id: User-supplied job ID override (empty string if none).
        user_query: The user's natural language simulation request.

    Returns:
        A job ID like ``job_a1b2c3d4__20260611_150405``, or the
        unchanged *base_id* if one was provided.
    """
    if base_id:
        return base_id

    uuid_part = f"job_{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{uuid_part}__{timestamp}"
