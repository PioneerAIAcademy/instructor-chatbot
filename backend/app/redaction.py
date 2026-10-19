"""Redact student identifiers before they leave for tracing (CLAUDE.md §9.2).

Instructors type student names, IDs, and situations into questions. The text
goes to OpenAI and Voyage (needed to answer), but the copies kept in Langfuse
should not hold identifiers. This masks:

- email addresses  -> [email]
- runs of 7+ digits, optionally split by spaces or dashes (student IDs,
  phone numbers) -> [number]

Names can't be found reliably by pattern, which is why the UI asks people not
to type them (§9.2) and the prompt never repeats them.

`mask_for_langfuse` is wired into the Langfuse client and the @observe
decorator context (app/langfuse.py), so it covers every trace, observation,
and generation, including the LlamaIndex bridge's `rag-llm` prompts.
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# 7+ digits, allowing single spaces or dashes between groups ("123 456 789").
_NUMBER_RE = re.compile(r"(?<![\w/.#?=&-])\d(?:[ -]?\d){6,}(?![\w/-])")


def redact(text: str) -> str:
    """Mask emails and long digit runs in `text`. URLs keep their digits: a
    digit run inside a URL path or query is not a student ID."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[email]", text)
    return _NUMBER_RE.sub("[number]", text)


def mask_for_langfuse(*, data: Any, **kwargs: Any) -> Any:
    """Langfuse `mask` hook: redact every string, however deeply nested."""
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, dict):
        return {k: mask_for_langfuse(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return type(data)(mask_for_langfuse(data=v) for v in data)
    return data
