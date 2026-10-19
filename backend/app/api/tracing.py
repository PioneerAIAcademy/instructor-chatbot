"""Langfuse tags and metadata for Instructor Assistant traces (CLAUDE.md §9.1).

One place for them, so the chat, blocked-input, draft-edit, and feedback
traces carry the same identifiers, and traces stay identifiable if the
Langfuse project is ever shared with another app.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

from langfuse import LangfuseOtelSpanAttributes, propagate_attributes

from app.engine.audience_guard import INSTRUCTOR_ROLE
from app.langfuse import langfuse, real_id

logger = logging.getLogger("uvicorn")

APP_TAG = "app:instructor-assistant"
ROLE_TAG = f"role:{INSTRUCTOR_ROLE}"
EVAL_SESSION_PREFIX = "eval-"
_CITATION_RE = re.compile(r"\[\^(\d+)\]")


def index_name() -> str:
    return os.getenv("PINECONE_INDEX_NAME", "")


def identity_tags() -> list[str]:
    """On every trace: which app, which audience."""
    return [APP_TAG, ROLE_TAG]


def eval_tags(session_id: str | None) -> list[str]:
    """`eval` and `eval_run:<id>` for eval traffic (session IDs starting
    `eval-`, as scripts/eval_answers.py sends), so dashboards can exclude it."""
    if session_id and session_id.startswith(EVAL_SESSION_PREFIX):
        run = session_id[len(EVAL_SESSION_PREFIX):] or "unknown"
        return ["eval", f"eval_run:{run}"]
    return []


def security_tag(is_suspicious: bool, details: dict) -> str:
    if not is_suspicious:
        return "security:clean"
    return f"security:risk_{str(details.get('risk_level', 'LOW')).lower()}"


def chat_tags(*, language: str, security: str, session_id: str | None) -> list[str]:
    """The §9.1 tag set for a `chat` trace."""
    return [
        *identity_tags(),
        f"index:{index_name()}",
        "feature:chat",
        "workflow:classic",
        f"language:{language}",
        security,
        *eval_tags(session_id),
    ]


def base_metadata() -> dict[str, Any]:
    """Metadata known when the request arrives."""
    return {
        "role": INSTRUCTOR_ROLE,
        "index_name": index_name(),
        "app_version": os.getenv("APP_VERSION") or None,
    }


def _meta(node: Any) -> dict:
    inner = getattr(node, "node", None)
    meta = getattr(inner, "metadata", None) if inner is not None else getattr(node, "metadata", None)
    return meta if isinstance(meta, dict) else {}


def answer_metadata(answer: str, source_nodes: Iterable[Any], *, completed: bool = True) -> dict[str, Any]:
    """Metadata about what the answer drew on (§9.1): counts by source, the
    slugs actually cited, and whether rerank left nothing to answer from.

    `completed` is False when no answer came back (synthesis failed, a
    timeout, a disconnect). The source fields are then None, not 0, so a
    failure isn't counted as a rerank miss (Q15)."""
    if not completed:
        return {
            "answer_completed": False,
            "sources_core": None,
            "sources_linked": None,
            "cited_slugs": [],
            "rerank_empty": None,
        }
    nodes = list(source_nodes or [])
    by_citation = {str(getattr(n, "citation_node_id", "")): _meta(n) for n in nodes}
    cited = []
    for number in dict.fromkeys(_CITATION_RE.findall(answer or "")):
        slug = by_citation.get(number, {}).get("slug")
        if slug and slug not in cited:
            cited.append(slug)
    sources = [_meta(n).get("source") for n in nodes]
    return {
        "answer_completed": True,
        "sources_core": sources.count("instructor-assistant"),
        "sources_linked": sources.count("instructor-assistant-linked"),
        "cited_slugs": cited,
        "rerank_empty": not nodes,
    }


# --- the per-request trace (langfuse 4.x) --------------------------------------------


def _ascii_id(value: str | None) -> str | None:
    """user_id / session_id must be US-ASCII and at most 200 characters."""
    if not value:
        return None
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return None
    return value[:200]


def _short_strings(metadata: dict[str, Any]) -> dict[str, str]:
    """Propagated (trace-level) metadata values are strings of at most 200 chars."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        text = str(value)
        if len(text) <= 200:
            out[key] = text
    return out


class RequestTrace:
    """One Langfuse trace for one request, held open across a streaming response.

    The root observation is created here, in the request handler. Work that
    runs later in the stream (the orchestrator, suggestions) attaches to it with
    `child_kwargs()` inside `propagate()`, so its observations nest under the
    root and carry the same tags, user, and session. `finish()` sets the output
    and closes the root. With tracing off, every method is a no-op and
    `trace_id` is None.
    """

    def __init__(
        self,
        name: str,
        *,
        input: Any,
        user_id: str | None,
        session_id: str | None,
        tags: list[str],
        metadata: dict[str, Any],
    ) -> None:
        self.name = name
        self.tags = list(tags)
        self._attrs = dict(
            user_id=_ascii_id(user_id),
            session_id=_ascii_id(session_id),
            tags=self.tags,
            trace_name=name,
            metadata=_short_strings(metadata),
        )
        self._ended = False
        with propagate_attributes(**self._attrs):
            self.root = langfuse.start_observation(name=name, input=input, metadata=metadata)
        self.root.set_trace_io(input=input)

    @property
    def trace_id(self) -> Optional[str]:
        return real_id(self.root.trace_id)

    def child_kwargs(self) -> dict[str, str]:
        """Pass to an @observe-decorated call that runs outside the root's
        context, so its observation nests under the root."""
        if not self.trace_id:
            return {}
        return {"langfuse_trace_id": self.trace_id, "langfuse_parent_observation_id": self.root.id}

    @contextmanager
    def propagate(self) -> Iterator[None]:
        """The root's trace attributes for observations created in this block."""
        with propagate_attributes(**self._attrs):
            yield

    def finish(
        self,
        *,
        output: Any,
        metadata: dict[str, Any] | None = None,
        extra_tags: list[str] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        """Record the output, final metadata, and any tags known only at the
        end, then close the root. Safe to call twice (the second is ignored).
        The root is ended even if recording fails: in langfuse 4.x an
        un-ended root is never exported, which would lose the whole trace."""
        if self._ended:
            return
        self._ended = True
        try:
            update: dict[str, Any] = {"output": output}
            if metadata is not None:
                update["metadata"] = metadata
            if level:
                update["level"] = level
            if status_message:
                update["status_message"] = status_message
            self.root.update(**update)
            self.root.set_trace_io(output=output)
            if extra_tags:
                self._add_late_tags(extra_tags, level)
        except Exception as exc:  # observability must never break the request
            logger.warning("[trace] finishing %s failed: %s", self.name, exc)
        finally:
            try:
                self.root.end()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("[trace] ending %s failed: %s", self.name, exc)

    def _add_late_tags(self, extra_tags: list[str], level: str | None) -> None:
        """Tags known only at the end (guard:audience_leak, outcome:*).

        Set on the root span itself (its trace-tags attribute, while the root
        is still open), so the trace carries them however the server merges
        tags. Also on an event under the root, created with the full tag set,
        so observation-level filters see them too."""
        tags = self.tags + [t for t in extra_tags if t not in self.tags]
        self.tags = tags
        otel_span = getattr(self.root, "_otel_span", None)
        if otel_span is not None:
            otel_span.set_attribute(LangfuseOtelSpanAttributes.TRACE_TAGS, tags)
        with propagate_attributes(**dict(self._attrs, tags=tags)):
            self.root.create_event(name="tags", metadata={"tags": extra_tags}, level=level)
