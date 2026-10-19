"""Redact student identifiers before they leave for tracing (CLAUDE.md §9.2).

Instructors type student names, IDs, and situations into questions. The text
goes to OpenAI and Voyage (needed to answer), but the copies kept in Langfuse
should not hold identifiers. This masks:

- email addresses  -> [email]
- runs of 7+ digits, optionally split by spaces, dots, or dashes (student
  IDs, phone numbers), wherever they appear outside a URL -> [number]
  (dates such as 2026-10-23 are left alone)

Names can't be found reliably by pattern, which is why the UI asks people not
to type them (§9.2) and the prompt never repeats them.

`mask_for_langfuse` is the Langfuse client's `mask` (app/langfuse.py). In
langfuse 4.x that covers the input, output, and metadata of every observation,
including the LlamaIndex bridge's `rag-llm` prompts.
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# 7+ digits, optionally led by "+" and split by single spaces, dots, or dashes:
# "12345678", "#12345678", "ID-12345678", "id=12345678", "801 555 1234",
# "+1.801.555.1234". A digit run glued to letters ("abc12345678") is left alone.
_NUMBER_RE = re.compile(r"(?<![\w])\+?\d(?:[ .-]?\d){6,}(?![\w])")
# Dates look like long digit runs but carry no identity: "2026-10-23",
# "2026.10.23", "23-10-2026", "10-23-2026".
_DATE_RE = re.compile(r"^(?:\d{4}[-.]\d{1,2}[-.]\d{1,2}|\d{1,2}[-.]\d{1,2}[-.]\d{4})$")


def _mask_numbers(text: str) -> str:
    def _sub(m: "re.Match[str]") -> str:
        return m.group(0) if _DATE_RE.match(m.group(0)) else "[number]"

    return _NUMBER_RE.sub(_sub, text)


def redact(text: str) -> str:
    """Mask emails and long digit runs in `text`. URLs are cut out first and
    kept whole (a digit run in a URL path or query is not a student ID), and
    dates are left alone."""
    if not text:
        return text
    from app.utils.links import find_links  # stdlib-only module

    out: list[str] = []
    cursor = 0
    def _mask(part: str) -> str:
        return _mask_numbers(_EMAIL_RE.sub("[email]", part))

    for link in find_links(text):
        out.append(_mask(text[cursor:link.start]))
        whole = text[link.start:link.end]
        if link.kind == "markdown" and link.label:
            # "[label](url)": the label is prose and gets masked; the URL doesn't.
            whole = "[" + _mask(link.label) + whole[1 + len(link.label):]
        out.append(whole)
        cursor = link.end
    out.append(_mask(text[cursor:]))
    return "".join(out)


def mask_for_langfuse(*, data: Any, **kwargs: Any) -> Any:
    """Langfuse `mask` hook: redact every string, however deeply nested."""
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, dict):
        return {k: mask_for_langfuse(data=v) for k, v in data.items()}
    if isinstance(data, tuple) and hasattr(data, "_fields"):  # namedtuple
        return type(data)(*(mask_for_langfuse(data=v) for v in data))
    if isinstance(data, (list, tuple)):
        return type(data)([mask_for_langfuse(data=v) for v in data])
    return data
