"""RetrievalOrchestrator — the entry point for the RAG path.

Classic path (CLAUDE.md §3): the plain CustomCondensePlusContextChatEngine,
then the deterministic grounding guards (citation coverage, decluster, link
integrity), then draft-fence citation hoisting, then the sign-in link
annotator (§8.3). Upstream's recency-aware
engine and missionary critic are not ported. The answer is drained before it
streams so the guards see the whole text. The post-retrieval role assertion
(Phase 1) lives in the engine's postprocessors.

Degradation ladder:
- A guard failure ships the unguarded draft.
- A synthesis failure (the LLM stream raised, or produced no text) raises
  SynthesisFailedError, so the stream shows the hiccup message instead of a
  blank answer with sources.
"""

import logging
import re
from typing import Any, Callable

from langfuse import observe

from app.langfuse import langfuse
from llama_index.core.callbacks import CallbackManager
from llama_index.core.settings import Settings

from app.engine import get_chat_engine
from app.engine.audience_guard import AudienceGuardPostprocessor
from app.engine.draft_normalizer import hoist_draft_citations
from app.engine.grounding_guard import apply_grounding_guards, ensure_citation_coverage
from app.engine.login_links import annotate_login_links
from app.utils.links import find_links
from app.utils.localization import LocalizationManager

logger = logging.getLogger("uvicorn")


class SynthesisFailedError(RuntimeError):
    """The LLM stream failed or produced no answer text."""


async def _drain_stream(response: Any) -> str:
    """Consume the engine's async_response_gen() into a single string, so the
    guards see the full text rather than chunks.

    Raises SynthesisFailedError if the stream raises: llama-index re-raises
    the OpenAI error from async_response_gen(), and a truncated answer must
    not ship as if it were complete."""
    chunks: list[str] = []
    try:
        async for token in response.async_response_gen():
            chunks.append(token)
    except Exception as exc:
        raise SynthesisFailedError(
            f"answer stream failed after {sum(len(c) for c in chunks)} chars: {exc}"
        ) from exc
    return "".join(chunks)


def _scope_callbacks(engine: Any, event_handler: Any) -> None:
    """Give this request's engine its own CallbackManager.

    `from_defaults` hands every engine the process-wide
    Settings.callback_manager. Appending the per-request EventCallbackHandler
    to it (as upstream does) leaks one handler per request and sends each
    request's status events to every concurrent stream. The per-request
    manager keeps the global handlers (the Langfuse bridge) and adds this
    request's handler, on the engine (rerank events) and its retriever
    (retrieve events). LLM events still go only to the global manager,
    because the LLM is shared.
    """
    global_handlers = list(getattr(Settings.callback_manager, "handlers", []) or [])
    manager = CallbackManager(handlers=[*global_handlers, event_handler])
    engine.callback_manager = manager
    retriever = getattr(engine, "_retriever", None)
    if retriever is not None:
        retriever.callback_manager = manager


class _GuardedStreamingResponse:
    """Minimal stand-in for StreamingAgentChatResponse used to ship the
    guarded answer back through the existing streaming path. Exposes the two
    attributes consumers depend on: async_response_gen() + source_nodes."""

    def __init__(self, text: str, source_nodes: list[Any]):
        self._text = text
        self.source_nodes = source_nodes

    @property
    def text(self) -> str:
        return self._text

    async def async_response_gen(self):
        # Chunk in ~40-char windows so typewriter UX feels live
        for i in range(0, len(self._text), 40):
            yield self._text[i : i + 40]


_CITATION_RE = re.compile(r"\[\^\d+\]")
_MARKDOWN_RE = re.compile(r"[#*_`>|~]+")


def _prose_for_detection(answer: str) -> str:
    """The answer's words only: URLs out (a markdown link keeps its label),
    citation markers and markdown symbols out. Long URLs otherwise dominate
    language detection."""
    parts: list[str] = []
    cursor = 0
    for link in find_links(answer):
        parts.append(answer[cursor:link.start])
        parts.append(link.label)  # "" for bare URLs and autolinks
        cursor = link.end
    parts.append(answer[cursor:])
    text = _CITATION_RE.sub(" ", "".join(parts))
    return " ".join(_MARKDOWN_RE.sub(" ", text).split())


def _label_language(answer: str, user_language: str | None) -> str:
    """The language for sign-in labels: the answer's own, so a label never
    clashes with the text around it. The request language can come from the
    settings menu (a short question isn't detected confidently), while the
    model answers in the question's language."""
    try:
        detected, confident = LocalizationManager.detect_language_confident(_prose_for_detection(answer))
        if confident:
            return detected
    except Exception:  # pragma: no cover - defensive
        pass
    return user_language or "en"


def _mark_observation_error(status_message: str) -> None:
    """Mark the current Langfuse observation ERROR. Never raises."""
    try:
        langfuse.update_current_span(level="ERROR", status_message=status_message)
    except Exception:  # pragma: no cover - defensive
        pass


def _ensure_minimum_citations(text: str, source_nodes: list[Any]) -> str:
    """Backward-compatible test hook for the citation coverage guard."""
    return ensure_citation_coverage(text, source_nodes)


class RetrievalOrchestrator:
    """Coordinates retrieval + synthesis + grounding guards for the RAG path.

    One instance per request. `audience_leak_dropped` is the number of nodes
    the post-retrieval audience guard has dropped so far. It reads the guard's
    live counter, so it is right at any moment: after success, after failure,
    and after a client disconnect cancels `run()` before its cleanup runs.
    Non-zero is a security finding; chat.py tags the trace with it.
    """

    def __init__(self) -> None:
        self._guard: AudienceGuardPostprocessor | None = None
        # Sign-in links in the final answer (trace metadata `login_links`), and
        # how many of them the annotator labeled (`login_links_labeled`).
        self.login_links = 0
        self.login_links_labeled = 0

    @property
    def audience_leak_dropped(self) -> int:
        return self._guard.dropped if self._guard is not None else 0

    @observe(name="retrieval-orchestrator")
    async def run(
        self,
        message,
        chat_history,
        filters,
        params,
        timezone,
        event_handler,
        emit_stage: Callable[[str], None] | None = None,
        user_language: str | None = "en",
    ):
        """Return a streaming-compatible response for `message`. A guard
        failure degrades to the unguarded draft; a synthesis failure raises
        SynthesisFailedError."""

        # Replace Langfuse's default arg/kwarg dump + Python object repr
        # output with a readable input. The output is a streaming response
        # whose text is produced lazily downstream; we mark it as such.
        try:
            langfuse.update_current_span(
                input=str(message),
                output="<streaming response; final text logged downstream>",
            )
        except Exception:  # pragma: no cover - defensive
            pass

        def _stage(name: str):
            if emit_stage is not None:
                try:
                    emit_stage(name)
                except Exception as exc:  # don't let emitter break the flow
                    logger.warning("[orch] emit_stage(%s) failed: %s", name, exc)

        _stage("retrieving")
        engine = get_chat_engine(filters=filters, params=params, timezone=timezone)
        guard = getattr(engine, "audience_guard", None)
        if not isinstance(guard, AudienceGuardPostprocessor):
            # Fail closed: an engine without its post-retrieval guard must not
            # retrieve at all (CLAUDE.md §0 rule 5).
            _mark_observation_error("chat engine has no audience guard")
            raise RuntimeError("chat engine has no audience guard; refusing to retrieve")
        self._guard = guard
        if event_handler is not None:
            _scope_callbacks(engine, event_handler)

        try:
            engine_response = await engine.astream_chat(message, chat_history)
            _stage("synthesizing")
            try:
                draft = await _drain_stream(engine_response)
                if not draft.strip():
                    raise SynthesisFailedError("answer stream produced no text")
            except SynthesisFailedError as exc:
                logger.error("[orch] synthesis failed: %s", exc)
                _mark_observation_error(f"synthesis failed: {exc}")
                raise
        finally:
            # Marked whether or not synthesis succeeded: a leak is a security
            # finding even when the answer then fails.
            if guard.dropped:
                _mark_observation_error(f"audience_leak: {guard.dropped} node(s) dropped")

        source_nodes = getattr(engine_response, "source_nodes", []) or []
        try:
            final_answer = apply_grounding_guards(
                draft,
                source_nodes,
                user_question=str(message),
                chat_history=chat_history,
            )
            final_answer = hoist_draft_citations(final_answer)
        except Exception as exc:
            logger.warning("[orch] grounding guards failed (%s) — returning unguarded draft", exc)
            final_answer = draft
        # Separate from the guards: even an unguarded draft gets its sign-in labels.
        try:
            # A function, so detection runs only if some link needs a label.
            answer_so_far = final_answer
            annotated = annotate_login_links(
                final_answer, lambda: _label_language(answer_so_far, user_language)
            )
            final_answer = annotated.text
            self.login_links, self.login_links_labeled = annotated.links, annotated.added
        except Exception as exc:
            logger.warning("[orch] sign-in annotator failed (%s) — links left unlabeled", exc)
        _stage("done")
        return _GuardedStreamingResponse(final_answer, source_nodes)
