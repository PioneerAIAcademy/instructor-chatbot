"""LlamaIndex -> Langfuse callback bridge.

Hooks llama-index `CBEventType.LLM` events and emits Langfuse generations
under the current `@observe`-wrapped trace. Drops in via
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

        return {
            "input": _read("prompt_tokens"),
            "output": _read("completion_tokens"),
            "total": _read("total_tokens"),
            "unit": "TOKENS",
        }
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
            p = payload or {}
            self._pending[event_id] = {
                "start": time.time(),
                "input_messages": p.get(EventPayload.MESSAGES)
                or p.get(EventPayload.PROMPT),
                "model": _extract_model_name(p),
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
            from langfuse import Langfuse  # type: ignore
            from langfuse.decorators import langfuse_context  # type: ignore
        except ImportError:
            return

        try:
            trace_id = langfuse_context.get_current_trace_id()
            if not trace_id:
                # No active @observe — drop silently.
                return

            p = payload or {}
            response = p.get(EventPayload.RESPONSE) or p.get(EventPayload.COMPLETION)
            output_text: Optional[str]
            if response is None:
                output_text = None
            else:
                # llama-index ChatResponse stringifies to "assistant: ..."
                output_text = str(response)

            usage = _extract_usage(response)
            input_repr = _stringify_messages(pending.get("input_messages"))

            client = Langfuse()  # picks up env vars (LANGFUSE_HOST/KEYS)
            client.generation(
                trace_id=trace_id,
                parent_observation_id=langfuse_context.get_current_observation_id(),
                name="rag-llm",
                model=pending.get("model"),
                start_time=pending.get("start"),
                end_time=time.time(),
                input=input_repr,
                output=output_text,
                usage=usage,
                metadata={
                    "source": "llama-index",
                    "event_id": event_id,
                    "event_type": str(event_type),
                },
            )
        except Exception as exc:
            logger.debug("[langfuse_li] end failed: %s", exc)
