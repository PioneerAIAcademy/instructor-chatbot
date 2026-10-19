"""Observability and privacy (CLAUDE.md §7 Phase 5, §9): trace tags and
metadata, eval tagging, redaction before tracing, and Sentry settings."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from llama_index.core.schema import TextNode

from app.api import tracing
from app.engine.custom_node_with_score import CustomNodeWithScore
from app.redaction import mask_for_langfuse, redact

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _node(n, slug, source="instructor-assistant"):
    node = CustomNodeWithScore(
        node=TextNode(text="t", id_=f"{slug}#{n}", metadata={"slug": slug, "source": source}), score=0.5
    )
    node.citation_node_id = str(n)
    return node


# --- redaction ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Maria (ID 12345678) emailed", "Maria (ID [number]) emailed"),
        ("write to maria.lopez@byupathway.edu today", "write to [email] today"),
        ("call 801-555-1234 or 801 555 1234", "call [number] or [number]"),
        ("Student 1234567", "Student [number]"),
        ("ticket #12345678 is stuck", "ticket #[number] is stuck"),
        ("ID-12345678 and id=12345678", "ID-[number] and id=[number]"),
        ("call +1.801.555.1234", "call [number]"),
        ("see [student 12345678](https://example.org/x)", "see [student [number]](https://example.org/x)"),
    ],
)
def test_redact_masks_emails_and_long_numbers(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Due October 21, 2026 at 11:59 PM",
        "Grades post 2026-10-23 (or 23-10-2026, 2026.10.23)",
        "Week 07, block 3, 2,500 points, code 123456",
        "https://byupathwayworldwideprod.sharepoint.com/sites/x/SitePages/123456789.aspx?id=9876543",
    ],
)
def test_redact_leaves_dates_short_numbers_and_urls(text):
    assert redact(text) == text


def test_mask_walks_nested_data():
    data = {"messages": [{"content": "ID 12345678"}, ("a@b.co", 3)], "n": 5}
    assert mask_for_langfuse(data=data) == {"messages": [{"content": "ID [number]"}, ("[email]", 3)], "n": 5}


def test_mask_keeps_namedtuples_and_tuples():
    from collections import namedtuple

    Pair = namedtuple("Pair", "who note")
    masked = mask_for_langfuse(data={"p": Pair("a@b.co", 12345678), "t": ("ID 12345678",)})
    assert masked["p"] == Pair("[email]", 12345678) and isinstance(masked["p"], Pair)
    assert masked["t"] == ("ID [number]",)


def test_the_client_and_observe_share_one_masked_client():
    from langfuse import get_client

    from app.langfuse import langfuse

    # langfuse 4.x masks input, output, and metadata of every observation.
    assert langfuse._mask is mask_for_langfuse
    # @observe uses get_client(): it must be the same masked client.
    assert get_client()._mask is mask_for_langfuse


def test_llamaindex_bridge_uses_the_shared_masked_client(monkeypatch):
    from unittest.mock import MagicMock

    from llama_index.core.callbacks.schema import CBEventType

    from app.langfuse import langfuse
    from app.utils import langfuse_llama_index as bridge

    generation = MagicMock()
    monkeypatch.setattr(langfuse, "get_current_trace_id", lambda: "a" * 32)
    monkeypatch.setattr(langfuse, "start_observation", lambda **kw: generation)
    handler = bridge.LangfuseLlamaIndexHandler()
    handler.on_event_start(CBEventType.LLM, payload={}, event_id="e1")
    handler.on_event_end(CBEventType.LLM, payload={}, event_id="e1")
    generation.end.assert_called_once()


def test_real_id_hides_disabled_tracing_ids():
    from app.langfuse import real_id

    assert real_id("0" * 32) is None and real_id(None) is None
    assert real_id("4bf92f3577b34da6a3ce929d0e0e4736") == "4bf92f3577b34da6a3ce929d0e0e4736"


# --- tags and metadata ----------------------------------------------------------------


def test_chat_tags_are_the_section_9_set(monkeypatch):
    monkeypatch.setenv("PINECONE_INDEX_NAME", "instructor-assistant")
    tags = tracing.chat_tags(language="pt", security="security:clean", session_id="abc")
    assert tags == [
        "app:instructor-assistant", "role:instructor", "index:instructor-assistant",
        "feature:chat", "workflow:classic", "language:pt", "security:clean",
    ]


def test_eval_sessions_get_eval_tags():
    assert tracing.eval_tags("eval-20261019T1200") == ["eval", "eval_run:20261019T1200"]
    assert tracing.eval_tags("apicheck-1") == [] and tracing.eval_tags(None) == []
    assert "eval_run:r1" in tracing.chat_tags(language="en", security="security:clean", session_id="eval-r1")


def test_security_tag():
    assert tracing.security_tag(False, {}) == "security:clean"
    assert tracing.security_tag(True, {"risk_level": "MEDIUM"}) == "security:risk_medium"


def test_base_metadata(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc1234")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "instructor-assistant")
    assert tracing.base_metadata() == {"role": "instructor", "index_name": "instructor-assistant", "app_version": "abc1234"}
    monkeypatch.delenv("APP_VERSION")
    assert tracing.base_metadata()["app_version"] is None


def test_answer_metadata_counts_sources_and_cited_slugs():
    nodes = [_node(1, "pay-ia"), _node(2, "linked--x", "instructor-assistant-linked"), _node(3, "ferpa-ia")]
    meta = tracing.answer_metadata("Paid on the 8th [^1]. See the page [^2]. Again [^1].", nodes)
    assert meta == {"answer_completed": True, "sources_core": 2, "sources_linked": 1,
                    "cited_slugs": ["pay-ia", "linked--x"], "rerank_empty": False}
    assert tracing.answer_metadata("Nothing found.", [])["rerank_empty"] is True


def test_failed_answer_is_not_counted_as_a_rerank_miss():
    meta = tracing.answer_metadata("", [], completed=False)
    assert meta["answer_completed"] is False
    assert meta["rerank_empty"] is None and meta["sources_core"] is None and meta["cited_slugs"] == []


# --- RequestTrace ----------------------------------------------------------------------


def _trace_with_mock_root():
    from unittest.mock import MagicMock

    trace = tracing.RequestTrace("chat", input="q", user_id="d", session_id="s",
                                 tags=["app:instructor-assistant"], metadata={})
    trace.root = MagicMock()
    return trace


def test_finish_ends_the_root_even_when_recording_fails():
    trace = _trace_with_mock_root()
    trace.root.update.side_effect = RuntimeError("bad payload")
    trace.finish(output="answer")
    trace.root.end.assert_called_once()
    trace.finish(output="again")  # the second call is ignored
    trace.root.end.assert_called_once()


def test_late_tags_go_on_the_root_span():
    from langfuse import LangfuseOtelSpanAttributes

    trace = _trace_with_mock_root()
    trace.finish(output="a", extra_tags=["guard:audience_leak"], level="ERROR")
    trace.root._otel_span.set_attribute.assert_called_once_with(
        LangfuseOtelSpanAttributes.TRACE_TAGS, ["app:instructor-assistant", "guard:audience_leak"]
    )
    trace.root.create_event.assert_called_once()
    # The tags are set before the root ends (attributes on an ended span are dropped).
    names = [c[0] for c in trace.root.method_calls]
    assert names.index("create_event") < names.index("end")


# --- the streaming response ------------------------------------------------------------


def test_stream_end_runs_once_even_if_the_body_is_never_sent():
    import asyncio

    from app.api.routers.vercel_response import VercelStreamResponse, _Once

    calls = []

    async def _end(text):
        calls.append(text)

    once = _Once(_end)
    asyncio.run(once("a"))
    asyncio.run(once("b"))
    assert calls == ["a"]

    calls.clear()
    response = VercelStreamResponse(None, None, None, None, on_stream_end=_end)

    async def _receive():
        await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def _send(message):
        raise OSError("client went away")  # before the body is iterated at all

    scope = {"type": "http", "asgi": {"spec_version": "2.3"}}
    with pytest.raises(BaseException):
        asyncio.run(response(scope, _receive, _send))
    assert calls == [""]


# --- the chat trace end to end (stubbed orchestrator) -------------------------------


def _client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routers import chat as chat_module
    from app.api.routers import vercel_response

    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("PINECONE_INDEX_NAME", "instructor-assistant")
    monkeypatch.setenv("APP_VERSION", "abc1234")
    monkeypatch.setattr(vercel_response, "TYPEWRITER_CHUNK_DELAY", 0.0)

    async def _suggest(*a, **k):
        return []

    monkeypatch.setattr(vercel_response.NextQuestionSuggestion, "suggest_next_questions", _suggest)

    async def _clean(text):
        return False, None, {}

    monkeypatch.setattr(chat_module.InputValidator, "validate_input_security_async", _clean)

    class _Answer:
        source_nodes = [_node(1, "pay-dates-for-worldwide-online-instructors-ia")]

        async def async_response_gen(self):
            yield "You're paid on the 8th and 23rd [^1]."

    class _Orchestrator:
        def __init__(self):
            self.audience_leak_dropped = 0
            self.login_links = 0
            self.login_links_labeled = 0

        async def run(self, *a, **k):
            return _Answer()

    monkeypatch.setattr(chat_module, "RetrievalOrchestrator", _Orchestrator)
    chat_module.limiter.reset()
    app = FastAPI()
    app.state.limiter = chat_module.limiter
    app.include_router(chat_module.chat_router, prefix="/api/v1/chat")
    return TestClient(app)


def test_chat_trace_gets_the_section_9_tags_and_metadata(monkeypatch, fake_traces):
    client = _client(monkeypatch)
    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "When do I get paid?"}]},
                    headers={"X-Session-ID": "eval-run42", "X-Device-ID": "device-1"})
    assert r.status_code == 200
    (trace,) = fake_traces
    assert trace.name == "chat" and trace.session_id == "eval-run42" and trace.user_id == "device-1"
    for tag in ("app:instructor-assistant", "role:instructor", "index:instructor-assistant", "feature:chat",
                "workflow:classic", "language:en", "security:clean", "eval", "eval_run:run42"):
        assert tag in trace.tags, tag
    assert trace.finished["output"].startswith("You're paid on the 8th")
    meta = trace.finished["metadata"]
    for key in ("role", "index_name", "sources_core", "sources_linked", "cited_slugs", "login_links",
                "login_links_labeled", "rerank_empty", "app_version"):
        assert key in meta, key
    assert meta["cited_slugs"] == ["pay-dates-for-worldwide-online-instructors-ia"]
    assert meta["sources_core"] == 1 and meta["rerank_empty"] is False and meta["app_version"] == "abc1234"


def test_thumbs_comment_is_redacted(monkeypatch):
    from app.api.routers import chat as chat_module

    client = _client(monkeypatch)
    scores = []
    monkeypatch.setattr(chat_module.langfuse, "create_score", lambda **kw: scores.append(kw))
    client.post("/api/v1/chat/thumbs_request",
                json={"trace_id": "t1", "value": "bad", "comment": "Wrong for student 12345678 (ana@x.org)"})
    assert scores[0]["comment"] == "Wrong for student [number] ([email])"


def test_failed_answer_trace_is_marked_not_completed(monkeypatch, fake_traces):
    from app.api.routers import chat as chat_module

    client = _client(monkeypatch)

    async def _fail(self, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_module.RetrievalOrchestrator, "run", _fail)
    client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "When do I get paid?"}]})
    (trace,) = fake_traces
    assert trace.finished is not None
    assert trace.finished["metadata"]["answer_completed"] is False
    assert trace.finished["metadata"]["rerank_empty"] is None  # not counted as a rerank miss
    assert trace.finished["level"] == "WARNING"


def _draft_body():
    return {"draft_type": "message", "instruction": "make it warmer",
            "selected_text": "Hello class.", "full_content": "Hello class. Welcome."}


def test_draft_edit_trace_input_is_what_the_model_saw(monkeypatch, fake_traces):
    from app.api.routers import chat as chat_module

    client = _client(monkeypatch)

    async def _low(text):
        return True, None, {"risk_level": "LOW"}

    seen = {}

    async def _rewrite(**kw):
        seen.update(kw)
        return "Hello, friends.", None, {}

    monkeypatch.setattr(chat_module.InputValidator, "validate_input_security_async", _low)
    monkeypatch.setattr(chat_module.InputValidator, "sanitize_input", lambda text: "SANITIZED")
    monkeypatch.setattr(chat_module, "rewrite_selected_text_with_llm", _rewrite)
    client.post("/api/v1/chat/draft/edit", json=_draft_body())
    (trace,) = fake_traces
    assert trace.input == "SANITIZED" and seen["instruction"] == "SANITIZED"


def test_draft_edit_trace_closes_when_the_rewrite_raises(monkeypatch, fake_traces):
    from fastapi.testclient import TestClient

    from app.api.routers import chat as chat_module

    _client(monkeypatch)

    async def _boom(**kw):
        raise RuntimeError("OpenAI 503")

    monkeypatch.setattr(chat_module, "rewrite_selected_text_with_llm", _boom)
    from fastapi import FastAPI

    app = FastAPI()
    app.state.limiter = chat_module.limiter
    app.include_router(chat_module.chat_router, prefix="/api/v1/chat")
    r = TestClient(app, raise_server_exceptions=False).post("/api/v1/chat/draft/edit", json=_draft_body())
    assert r.status_code == 500
    (trace,) = fake_traces
    assert trace.finished["level"] == "ERROR" and trace.finished["output"] is None


def test_suggestions_and_draft_edit_are_spans_not_generations():
    """The rag-llm bridge already records each LLM call as a generation, with
    its cost. A second generation for the same call would count it twice."""
    import inspect

    from app.api.services import draft_edit, suggestion

    for module in (draft_edit, suggestion):
        source = inspect.getsource(module)
        assert 'as_type="generation"' not in source and "update_current_generation" not in source


def test_no_user_text_goes_into_trace_metadata(monkeypatch, fake_traces):
    """Metadata describes the answer, not the question. (langfuse 4.x masks
    metadata too, but names can't be masked, so the question stays out.)"""
    client = _client(monkeypatch)
    secret = "Maria Fernandez 12345678"
    client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": f"Can I tell {secret}'s mom her grade?"}]})
    (trace,) = fake_traces
    assert "Maria" not in str(trace.metadata) and "Maria" not in str(trace.finished["metadata"])


# --- Sentry ----------------------------------------------------------------------------


def test_sentry_never_sends_bodies_locals_or_raw_identifiers():
    env = {
        "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
        "ENVIRONMENT": "dev", "MODEL_PROVIDER": "openai", "MODEL": "gpt-4o-mini",
        "EMBEDDING_MODEL": "text-embedding-3-large", "EMBEDDING_DIM": "3072",
        "OPENAI_API_KEY": "placeholder", "VOYAGE_API_KEY": "placeholder",
        "PINECONE_INDEX_NAME": "instructor-assistant",
        "SENTRY_DSN": "https://public@o0.ingest.sentry.io/0",
    }
    code = (
        "import main, sentry_sdk\n"
        "o = sentry_sdk.get_client().options\n"
        "print(o['send_default_pii'], o['max_request_body_size'], o['include_local_variables'])\n"
        "e = {'exception': {'values': [{'value': 'failed for ana@x.org id 12345678'}]}, 'logentry': {'message': 'm 7654321'},\n"
        "     'message': 'msg 2345678', 'breadcrumbs': {'values': [{'message': 'q from bo@y.org', 'data': {'q': 'ID 3456789'}}]}}\n"
        "print(o['before_send'](e, {}), o['before_breadcrumb']({'message': 'log 4567890'}, {}))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    lines = result.stdout.strip().splitlines()
    assert lines[-2] == "False never False"
    for raw in ("ana@x.org", "12345678", "7654321", "2345678", "bo@y.org", "3456789", "4567890"):
        assert raw not in lines[-1], raw
