"""Smoke tests for the LangfuseLlamaIndexHandler RAG instrumentation bridge.

Verifies that the handler:
  - Instantiates cleanly without a langfuse import
  - Is a valid BaseCallbackHandler (drops into CallbackManager)
  - No-ops silently when no Langfuse trace is active
  - Tracks event start/end pairs in self._pending
  - Drops non-LLM events
  - Honors the LANGFUSE_LLAMAINDEX_ENABLED=false off-switch
"""

import os
from unittest.mock import patch

from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload

from app.utils.langfuse_llama_index import LangfuseLlamaIndexHandler


def test_handler_is_base_callback_handler():
    handler = LangfuseLlamaIndexHandler()
    assert isinstance(handler, BaseCallbackHandler)


def test_non_llm_events_ignored():
    handler = LangfuseLlamaIndexHandler()
    handler.on_event_start(CBEventType.EMBEDDING, payload={}, event_id="abc")
    assert "abc" not in handler._pending
    handler.on_event_end(CBEventType.RETRIEVE, payload={}, event_id="abc")
    # No exception, no entries added or removed.


def test_llm_event_start_buffers_input():
    handler = LangfuseLlamaIndexHandler()
    payload = {
        EventPayload.MESSAGES: [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ],
        EventPayload.MODEL_NAME: "gpt-4o-mini",
    }
    handler.on_event_start(CBEventType.LLM, payload=payload, event_id="evt1")
    entry = handler._pending["evt1"]
    assert entry["model"] == "gpt-4o-mini"
    assert entry["input_messages"][1]["content"] == "Hello"
    assert "start" in entry


def test_llm_event_end_without_active_trace_is_silent():
    # No @observe-wrapped call site -> get_current_trace_id returns None.
    handler = LangfuseLlamaIndexHandler()
    handler.on_event_start(
        CBEventType.LLM,
        payload={EventPayload.MESSAGES: [{"role": "user", "content": "hi"}]},
        event_id="evt2",
    )
    # Force trace_id None.
    with patch(
        "langfuse.decorators.langfuse_context.get_current_trace_id",
        return_value=None,
    ):
        handler.on_event_end(
            CBEventType.LLM,
            payload={EventPayload.RESPONSE: "world"},
            event_id="evt2",
        )
    # Pending was popped on entry to on_event_end.
    assert "evt2" not in handler._pending


def test_off_switch_skips_buffering():
    with patch.dict(os.environ, {"LANGFUSE_LLAMAINDEX_ENABLED": "false"}):
        handler = LangfuseLlamaIndexHandler()
        handler.on_event_start(
            CBEventType.LLM,
            payload={EventPayload.MESSAGES: [{"role": "user", "content": "hi"}]},
            event_id="evt3",
        )
        assert "evt3" not in handler._pending


def test_end_without_matching_start_is_safe():
    handler = LangfuseLlamaIndexHandler()
    # No start event for this id -> end should be a no-op (no KeyError).
    handler.on_event_end(
        CBEventType.LLM,
        payload={EventPayload.RESPONSE: "hi"},
        event_id="unknown",
    )


def test_trace_lifecycle_methods_are_safe():
    handler = LangfuseLlamaIndexHandler()
    handler.start_trace(trace_id="t")
    handler.end_trace(trace_id="t", trace_map={})
