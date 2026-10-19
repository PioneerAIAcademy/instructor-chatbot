"""The /api/v1/chat stream contract, as code (backend/API.md is the prose).

Used by tests/test_api_contract.py (offline, against the real stream code)
and scripts/api_check.py (live, against a running server), so API.md, the
tests, and the live check describe the same thing. Change all three together.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable, Iterable

# What /api/docs (openapi.json) must list: the API routes and nothing else.
KEPT_ROUTES = frozenset({
    "/api/v1/chat",
    "/api/v1/chat/draft/edit",
    "/api/v1/chat/thumbs_request",
    "/api/v1/chat/feedback/general",
    "/api/v1/chat/config",
    "/api/health",
    "/api/health/ready",
})


def client_headers(session_prefix: str) -> dict[str, str]:
    """Headers a script sends: a fresh X-Session-ID with `session_prefix`,
    UTC, and X-API-Key from API_KEYS when set (never printed)."""
    headers = {"X-Session-ID": f"{session_prefix}-{uuid.uuid4()}", "X-Timezone": "UTC"}
    key = next((k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()), "")
    if key:
        headers["X-API-Key"] = key
    return headers

# Annotation types the chat stream may send, in the order they arrive.
ANNOTATION_ORDER = ("events", "date_spans", "user_language", "sources", "suggested_questions")
# The ones every successful RAG answer carries. (date_spans only when the answer has dates;
# suggested_questions only when generation succeeded; events are status ticks.)
REQUIRED_ON_ANSWER = ("user_language", "sources")

SOURCE_NODE_FIELDS = {
    "id": str,
    "citation_node_id": str,
    "metadata": dict,
    "score": (float, int, type(None)),
    "text": str,
    "url": (str, type(None)),
}
# Metadata keys the frontend and the evals rely on (§1 index contract).
SOURCE_METADATA_KEYS = ("url", "title", "slug", "source", "role", "sequence")


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _check_events(data: Any) -> list[str]:
    return [] if isinstance(data, dict) and isinstance(data.get("title"), str) else ["events.data.title must be a string"]


def _check_date_spans(data: Any) -> list[str]:
    if not isinstance(data, dict) or not _is_str_list(data.get("phrases")):
        return ["date_spans.data.phrases must be a list of strings"]
    if not isinstance(data.get("language"), (str, type(None))):
        return ["date_spans.data.language must be a string or null"]
    return []


def _check_user_language(data: Any) -> list[str]:
    ok = isinstance(data, dict) and isinstance(data.get("language"), str) and data["language"]
    return [] if ok else ["user_language.data.language must be a non-empty string"]


def _check_sources(data: Any) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return ["sources.data.nodes must be a list"]
    problems: list[str] = []
    for i, node in enumerate(data["nodes"]):
        if not isinstance(node, dict):
            problems.append(f"sources node {i} is not an object")
            continue
        for field, kind in SOURCE_NODE_FIELDS.items():
            if field not in node:
                problems.append(f"sources node {i} lacks {field}")
            elif not isinstance(node[field], kind):
                problems.append(f"sources node {i}: {field} has type {type(node[field]).__name__}")
        meta = node.get("metadata") or {}
        for key in SOURCE_METADATA_KEYS:
            if key not in meta:
                problems.append(f"sources node {i}: metadata lacks {key}")
        if node.get("url") != meta.get("url"):
            problems.append(f"sources node {i}: url differs from metadata.url")
    return problems


def _check_suggested(data: Any) -> list[str]:
    return [] if _is_str_list(data) else ["suggested_questions.data must be a list of strings"]


CHECKERS: dict[str, Callable[[Any], list[str]]] = {
    "events": _check_events,
    "date_spans": _check_date_spans,
    "user_language": _check_user_language,
    "sources": _check_sources,
    "suggested_questions": _check_suggested,
}


def parse_lines(lines: Iterable[str]) -> tuple[list[str], list[dict], list[str]]:
    """(text_chunks, annotations, problems) from data-stream lines.

    Accepts exactly two prefixes: `0:` (a JSON string of answer text) and
    `8:` (a JSON list of annotation objects). Blank lines are the flush
    padding and are skipped. Anything else is a contract problem.
    """
    text: list[str] = []
    annotations: list[dict] = []
    problems: list[str] = []
    for raw in lines:
        line = raw.strip("\r")
        if not line:
            continue
        prefix, sep, payload = line.partition(":")
        if not sep or prefix not in ("0", "8"):
            problems.append(f"unexpected line prefix: {line[:40]!r}")
            continue
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            problems.append(f"line is not JSON after the prefix: {line[:40]!r}")
            continue
        if prefix == "0":
            if isinstance(value, str):
                text.append(value)
            else:
                problems.append("a 0: line must carry a JSON string")
        elif isinstance(value, list) and all(isinstance(a, dict) for a in value):
            annotations.extend(value)
        else:
            problems.append("an 8: line must carry a JSON list of objects")
    return text, annotations, problems


def check_annotations(annotations: list[dict], *, expect_answer: bool = True) -> list[str]:
    """Contract problems in a stream's annotations (empty list = conforms)."""
    problems: list[str] = []
    seen: list[str] = []
    for a in annotations:
        kind = a.get("type")
        if kind not in CHECKERS:
            problems.append(f"undocumented annotation type: {kind!r}")
            continue
        if "trace_id" not in a or not isinstance(a["trace_id"], (str, type(None))):
            problems.append(f"{kind}: trace_id must be present (string or null)")
        problems += CHECKERS[kind](a.get("data"))
        seen.append(kind)
    # After the status ticks, the post-answer annotations come once each, in order.
    tail = [k for k in seen if k != "events"]
    if len(tail) != len(set(tail)):
        problems.append(f"an annotation type repeats: {tail}")
    order = [ANNOTATION_ORDER.index(k) for k in tail]
    if order != sorted(order):
        problems.append(f"annotations out of order: {tail}")
    if expect_answer:
        for kind in REQUIRED_ON_ANSWER:
            if kind not in seen:
                problems.append(f"missing {kind} annotation")
    return problems
