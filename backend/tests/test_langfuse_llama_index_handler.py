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


def _with_active_trace(generation):
    """Patch the shared client: an active trace, and start_observation -> generation."""
    from app.langfuse import langfuse

    return (
        patch.object(langfuse, "get_current_trace_id", return_value="a" * 32),
        patch.object(langfuse, "start_observation", return_value=generation),
    )


def test_llm_event_start_opens_a_generation_under_the_active_trace():
    from unittest.mock import MagicMock

    handler = LangfuseLlamaIndexHandler()
    payload = {
        EventPayload.MESSAGES: [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ],
        EventPayload.MODEL_NAME: "gpt-4o-mini",
    }
    generation = MagicMock()
    trace_patch, start_patch = _with_active_trace(generation)
    with trace_patch, start_patch as start:
        handler.on_event_start(CBEventType.LLM, payload=payload, event_id="evt1")
    kwargs = start.call_args.kwargs
    assert kwargs["name"] == "rag-llm" and kwargs["as_type"] == "generation"
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["input"][1]["content"] == "Hello"
    assert handler._pending["evt1"]["generation"] is generation


def test_llm_event_end_closes_the_generation_with_output_and_usage():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    handler = LangfuseLlamaIndexHandler()
    generation = MagicMock()
    trace_patch, start_patch = _with_active_trace(generation)
    with trace_patch, start_patch:
        handler.on_event_start(CBEventType.LLM, payload={EventPayload.MESSAGES: []}, event_id="evt3")
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    response = SimpleNamespace(raw=SimpleNamespace(usage=usage), __str__=lambda self: "assistant: hi")
    handler.on_event_end(CBEventType.LLM, payload={EventPayload.RESPONSE: response}, event_id="evt3")
    generation.update.assert_called_once()
    assert generation.update.call_args.kwargs["usage_details"] == {"input": 10, "output": 5, "total": 15}
    generation.end.assert_called_once()
    assert "evt3" not in handler._pending


def test_llm_event_without_active_trace_is_silent():
    # No active trace (or tracing off): nothing is opened, nothing is pending.
    handler = LangfuseLlamaIndexHandler()
    handler.on_event_start(
        CBEventType.LLM,
        payload={EventPayload.MESSAGES: [{"role": "user", "content": "hi"}]},
        event_id="evt2",
    )
    assert "evt2" not in handler._pending
    handler.on_event_end(CBEventType.LLM, payload={EventPayload.RESPONSE: "world"}, event_id="evt2")


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
