"""LlamaIndex -> Langfuse callback bridge.

Hooks llama-index `CBEventType.LLM` events and emits Langfuse generations
(`rag-llm`) under the currently active observation (langfuse 4.x: the
generation starts when the LLM call starts, as a child of the active span,
and ends when it ends). Drops in via
`Settings.callback_manager` (which MUST be initialized BEFORE
`Settings.llm` per lesson #62 — the OpenAI llama-index constructor
captures `Settings.callback_manager` at instantiation time and caches
None if not present, breaking every later request).

Why custom and not `langfuse.llama_index.LlamaIndexCallbackHandler`:
The langfuse v2.60 shipped integration eagerly imports
`llama_index.core.workflow.Context`, which exists in `llama-index-core
>=0.11` but not in our pinned `0.10.58`. Upgrading llama-index-core is
high-risk (API surface changes touch the chat engine, retrievers,
reranker — every layer). This bridge sidesteps the version coupling.

Coverage: LLM events specifically — the CONDENSE prompt and the
SYNTHESIZE prompt that `CustomCondensePlusContextChatEngine` runs per
RAG request. Embedding, reranking, and retrieval events are visible
through llama-index's own logging today; only the LLM calls themselves
were the missing puzzle piece. Toggle off entirely with env var
`LANGFUSE_LLAMAINDEX_ENABLED=false` if traces get noisy.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("LANGFUSE_LLAMAINDEX_ENABLED", "true").lower() != "false"


def _stringify_messages(messages: Any) -> Any:
    """Best-effort serialization of llama-index ChatMessage list."""
    if messages is None:
        return None
    try:
        if isinstance(messages, list):
            return [
                {
                    "role": (
                        getattr(m, "role", None)
                        or (m.get("role") if isinstance(m, dict) else None)
                    ),
                    "content": (
                        getattr(m, "content", None)
                        or (m.get("content") if isinstance(m, dict) else str(m))
                    ),
                }
                for m in messages
            ]
        return str(messages)
    except Exception:
        return str(messages)


def _extract_usage(response: Any) -> Optional[Dict[str, Any]]:
    """Pull prompt/completion/total tokens from a llama-index ChatResponse."""
    if response is None:
        return None
    try:
        raw = getattr(response, "raw", None)
        if raw is None:
            return None
        raw_usage = getattr(raw, "usage", None) or (
            raw.get("usage") if isinstance(raw, dict) else None
        )
        if not raw_usage:
            return None

        def _read(key: str) -> Optional[int]:
            v = getattr(raw_usage, key, None)
            if v is None and isinstance(raw_usage, dict):
                v = raw_usage.get(key)
            return v

        usage = {
            "input": _read("prompt_tokens"),
            "output": _read("completion_tokens"),
            "total": _read("total_tokens"),
        }
        # langfuse 4.x usage_details: token counts only, as ints.
        return {k: int(v) for k, v in usage.items() if isinstance(v, (int, float))} or None
    except Exception:
        return None


def _extract_model_name(payload: Dict[str, Any]) -> Optional[str]:
    """Best-effort model-name fetch from llama-index payloads."""
    model = payload.get(EventPayload.MODEL_NAME)
    if isinstance(model, str) and model:
        return model
    serialized = payload.get(EventPayload.SERIALIZED)
    if isinstance(serialized, dict):
        v = serialized.get("model") or serialized.get("model_name")
        if isinstance(v, str) and v:
            return v
    return None


class LangfuseLlamaIndexHandler(BaseCallbackHandler):
    """Bridges llama-index `CBEventType.LLM` events into Langfuse.

    For each LLM call:
      - `on_event_start`: capture start time + prompt/messages + model
      - `on_event_end`: emit a `generation` observation under the
        current trace via the Langfuse decorator API

    Silent no-op when:
      - `LANGFUSE_LLAMAINDEX_ENABLED=false`
      - The Langfuse SDK isn't reachable
      - No active `@observe` trace exists (e.g., this LLM call happened
        outside a tracked request path)

    Any exception during emission is logged at DEBUG and swallowed —
    observability MUST NEVER break the request flow.
    """

    def __init__(self) -> None:
        super().__init__(
            event_starts_to_ignore=[],
            event_ends_to_ignore=[],
        )
        # event_id -> { start, input_messages, model_name }
        self._pending: Dict[str, Dict[str, Any]] = {}

    # llama-index "trace" is its own request-scoped concept, distinct
    # from a Langfuse trace. We don't bridge these — Langfuse traces
    # are opened by @observe on the FastAPI endpoint.
    def start_trace(self, trace_id: Optional[str] = None) -> None:
        return

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, list]] = None,
    ) -> None:
        return

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        if event_type != CBEventType.LLM or not _enabled():
            return event_id
        try:
            from app.langfuse import langfuse, real_id

            if not real_id(langfuse.get_current_trace_id()):
                return event_id  # no active trace (or tracing off): nothing to attach to
            p = payload or {}
            messages = p.get(EventPayload.MESSAGES) or p.get(EventPayload.PROMPT)
            self._pending[event_id] = {
                "start": time.time(),
                "generation": langfuse.start_observation(
                    name="rag-llm",
                    as_type="generation",
                    model=_extract_model_name(p),
                    input=_stringify_messages(messages),
                    metadata={"source": "llama-index", "event_id": event_id},
                ),
            }
        except Exception as exc:
            logger.debug("[langfuse_li] start failed: %s", exc)
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        if event_type != CBEventType.LLM or not _enabled():
            return
        pending = self._pending.pop(event_id, None)
        if pending is None:
            return
        try:
            p = payload or {}
            response = p.get(EventPayload.RESPONSE) or p.get(EventPayload.COMPLETION)
            # llama-index ChatResponse stringifies to "assistant: ..."
            output_text: Optional[str] = None if response is None else str(response)
            generation = pending["generation"]
            generation.update(output=output_text, usage_details=_extract_usage(response))
            generation.end()
        except Exception as exc:
            logger.debug("[langfuse_li] end failed: %s", exc)
