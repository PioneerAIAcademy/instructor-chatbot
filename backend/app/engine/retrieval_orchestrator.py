"""RetrievalOrchestrator — the entry point for the RAG path.

Classic path (CLAUDE.md §3): the plain CustomCondensePlusContextChatEngine,
then the deterministic grounding guards (citation coverage, decluster, link
integrity), then draft-fence citation hoisting. Upstream's recency-aware
engine and missionary critic are not ported. The answer is drained before it
streams so the guards see the whole text; the sign-in link annotator
(Phase 3) and the post-retrieval role assertion (Phase 1) slot in here.

Degradation ladder:
- A guard failure ships the unguarded draft.
- A synthesis failure (the LLM stream raised, or produced no text) raises
  SynthesisFailedError, so the stream shows the hiccup message instead of a
  blank answer with sources.
"""

import logging
from typing import Any, Callable

from langfuse.decorators import observe
from llama_index.core.callbacks import CallbackManager
from llama_index.core.settings import Settings

from app.engine import get_chat_engine
from app.engine.audience_guard import audience_guard_of
from app.engine.draft_normalizer import hoist_draft_citations
from app.engine.grounding_guard import apply_grounding_guards, ensure_citation_coverage

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

    def __init__(self, text: str, source_nodes: list[Any], audience_leak_dropped: int = 0):
        self._text = text
        self.source_nodes = source_nodes
        # Nodes the post-retrieval audience guard dropped. Non-zero is a
        # security finding; chat.py tags the trace with it.
        self.audience_leak_dropped = audience_leak_dropped

    @property
    def text(self) -> str:
        return self._text

    async def async_response_gen(self):
        # Chunk in ~40-char windows so typewriter UX feels live
        for i in range(0, len(self._text), 40):
            yield self._text[i : i + 40]


def _ensure_minimum_citations(text: str, source_nodes: list[Any]) -> str:
    """Backward-compatible test hook for the citation coverage guard."""
    return ensure_citation_coverage(text, source_nodes)


class RetrievalOrchestrator:
    """Coordinates retrieval + synthesis + grounding guards for the RAG path."""

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
    ):
        """Return a streaming-compatible response for `message`. A guard
        failure degrades to the unguarded draft; a synthesis failure raises
        SynthesisFailedError."""

        # Replace Langfuse's default arg/kwarg dump + Python object repr
        # output with a readable input. The output is a streaming response
        # whose text is produced lazily downstream; we mark it as such.
        try:
            from langfuse.decorators import langfuse_context  # type: ignore

            langfuse_context.update_current_observation(
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
        if event_handler is not None:
            _scope_callbacks(engine, event_handler)
        engine_response = await engine.astream_chat(message, chat_history)
        _stage("synthesizing")

        try:
            draft = await _drain_stream(engine_response)
            if not draft.strip():
                raise SynthesisFailedError("answer stream produced no text")
        except SynthesisFailedError as exc:
            logger.error("[orch] synthesis failed: %s", exc)
            try:
                from langfuse.decorators import langfuse_context  # type: ignore

                langfuse_context.update_current_observation(
                    level="ERROR", status_message=f"synthesis failed: {exc}"
                )
            except Exception:  # pragma: no cover - defensive
                pass
            raise

        source_nodes = getattr(engine_response, "source_nodes", []) or []
        guard = audience_guard_of(engine)
        audience_leak_dropped = guard.dropped if guard is not None else 0
        if audience_leak_dropped:
            try:
                from langfuse.decorators import langfuse_context  # type: ignore

                langfuse_context.update_current_observation(
                    level="ERROR",
                    status_message=f"audience_leak: {audience_leak_dropped} node(s) dropped",
                )
            except Exception:  # pragma: no cover - defensive
                pass
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
        _stage("done")
        return _GuardedStreamingResponse(final_answer, source_nodes, audience_leak_dropped)
