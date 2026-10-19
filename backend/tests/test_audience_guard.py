"""Audience isolation (CLAUDE.md §7 Phase 1): filter shape, the index/host
boot guard, and the post-retrieval role assertion.

A guard firing is a finding. Never loosen one of these tests to make it pass.
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.vector_stores.types import FilterOperator

from app.engine import audience_guard
from app.engine.audience_guard import (
    AudienceGuardPostprocessor,
    IndexConfigError,
    assert_instructor_nodes,
    check_index_config,
    is_denied_index_name,
    is_instructor_metadata,
    instructor_filters,
)
from app.engine.custom_condense_plus_context import source_label

BACKEND_DIR = Path(__file__).resolve().parents[1]
HOST = "instructor-assistant-a1b2c3d.svc.aped-4627-b74a.pinecone.io"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("RETRIEVAL_SOURCES", "ALLOWED_INDEX_NAMES", "PINECONE_INDEX_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PINECONE_INDEX_NAME", "instructor-assistant")


def _by_key(filters):
    return {f.key: f for f in filters.filters}


def _node(role="instructor", source="instructor-assistant", slug="pay-dates-ia"):
    meta = {"slug": slug}
    if role is not None:
        meta["role"] = role
    if source is not None:
        meta["source"] = source
    return NodeWithScore(node=TextNode(text=f"{slug} text", id_=f"{slug}#0001", metadata=meta), score=0.8)


# --- filter ------------------------------------------------------------------


def test_filter_is_role_instructor_and_source_in_defaults():
    f = instructor_filters()

    assert f.condition == "and"
    by_key = _by_key(f)
    assert set(by_key) == {"role", "source"}
    assert by_key["role"].value == "instructor"
    assert by_key["role"].operator == FilterOperator.EQ
    assert by_key["source"].operator == FilterOperator.IN
    assert by_key["source"].value == ["instructor-assistant", "instructor-assistant-linked"]


def test_retrieval_sources_env_narrows_source_filter(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_SOURCES", "instructor-assistant")
    assert _by_key(instructor_filters())["source"].value == ["instructor-assistant"]


def test_blank_retrieval_sources_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_SOURCES", " , ")
    assert len(_by_key(instructor_filters())["source"].value) == 2


# --- index / host boot guard -----------------------------------------------------


def test_allowed_index_passes():
    assert check_index_config() == "instructor-assistant"


def test_missionary_index_is_refused():
    with pytest.raises(IndexConfigError, match="Missionary"):
        check_index_config("pathway", "")


def test_missionary_index_is_refused_even_when_allow_listed(monkeypatch):
    monkeypatch.setenv("ALLOWED_INDEX_NAMES", "instructor-assistant,pathway")
    with pytest.raises(IndexConfigError):
        check_index_config("instructor-assistant", "")


@pytest.mark.parametrize(
    "name", ["pathway-staging", "pathway_v2", "PATHWAY", "missionary-assistant", "pathway-missionaries"]
)
def test_missionary_index_variants_are_refused_even_when_allow_listed(monkeypatch, name):
    monkeypatch.setenv("ALLOWED_INDEX_NAMES", f"instructor-assistant,{name}")
    with pytest.raises(IndexConfigError):
        check_index_config(name, "")


@pytest.mark.parametrize("name", ["instructor-assistant", "instructor-assistant-staging", "pathwaysomething"])
def test_deny_list_does_not_catch_unrelated_names(name):
    # "pathwaysomething" isn't a copy named after the missionary index; the
    # allow-list (not the deny-list) is what stops unknown names.
    assert is_denied_index_name(name) is False


def test_unlisted_index_is_refused():
    with pytest.raises(IndexConfigError, match="ALLOWED_INDEX_NAMES"):
        check_index_config("some-other-index", "")


def test_staging_index_passes_when_allow_listed(monkeypatch):
    monkeypatch.setenv("ALLOWED_INDEX_NAMES", "instructor-assistant,instructor-assistant-staging")
    assert check_index_config("instructor-assistant-staging", "") == "instructor-assistant-staging"


def test_missing_index_name_is_refused(monkeypatch):
    monkeypatch.delenv("PINECONE_INDEX_NAME")
    with pytest.raises(IndexConfigError, match="not set"):
        check_index_config()


@pytest.mark.parametrize("host", [HOST, f"https://{HOST}", f"{HOST}:443", HOST.upper()])
def test_matching_host_passes(host):
    assert check_index_config("instructor-assistant", host) == "instructor-assistant"


@pytest.mark.parametrize(
    "host",
    [
        "pathway-a1b2c3d.svc.aped-4627-b74a.pinecone.io",  # the missionary index
        "instructor-assistant-staging-a1b2c3d.svc.x.pinecone.io",  # prefix match is not enough
        "instructor-assistant-a1b2c3d.svc.example.com",  # not a Pinecone host
        "instructor-assistant.svc.x.pinecone.io",  # no project id
    ],
)
def test_mismatched_host_is_refused(host):
    with pytest.raises(IndexConfigError, match="PINECONE_INDEX_HOST"):
        check_index_config("instructor-assistant", host)


def test_error_messages_never_contain_the_key(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "pcsk_SECRET_VALUE")
    with pytest.raises(IndexConfigError) as excinfo:
        check_index_config("pathway", "")
    assert "SECRET" not in str(excinfo.value)


def test_vector_store_refuses_bad_index_before_building(monkeypatch):
    from app.engine import vectordb

    monkeypatch.setenv("PINECONE_API_KEY", "placeholder")
    monkeypatch.setenv("PINECONE_ENVIRONMENT", "us-east-1")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "pathway")
    monkeypatch.setattr(vectordb, "_store_cache", None)
    with patch("pinecone.Pinecone") as client:
        with pytest.raises(IndexConfigError):
            vectordb.get_vector_store()
    client.assert_not_called()  # refused before any client is built


def test_vector_store_refuses_mismatched_host(monkeypatch):
    from app.engine import vectordb

    monkeypatch.setenv("PINECONE_API_KEY", "placeholder")
    monkeypatch.setenv("PINECONE_ENVIRONMENT", "us-east-1")
    monkeypatch.setattr(vectordb, "PINECONE_INDEX_HOST", "pathway-a1b2c3d.svc.x.pinecone.io")
    monkeypatch.setattr(vectordb, "_store_cache", None)
    with patch("pinecone.Pinecone") as client:
        with pytest.raises(IndexConfigError):
            vectordb.get_vector_store()
    client.assert_not_called()


def test_vector_store_checks_on_cache_miss_not_every_hit(monkeypatch):
    from app.engine import vectordb

    monkeypatch.setenv("PINECONE_API_KEY", "placeholder")
    monkeypatch.setenv("PINECONE_ENVIRONMENT", "us-east-1")
    monkeypatch.setattr(vectordb, "_store_cache", None)
    monkeypatch.setattr(vectordb, "PINECONE_STORE_CACHE_ENABLED", True)
    with patch("pinecone.Pinecone"), \
         patch.object(vectordb, "PineconeVectorStore"), \
         patch("app.engine.audience_guard.check_index_config", wraps=check_index_config) as check:
        vectordb.get_vector_store()
        vectordb.get_vector_store()
    assert check.call_count == 1


def _boot(index_name: str, host: str = "", voyage_key: str = "placeholder") -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "ENVIRONMENT": "dev",
        "MODEL_PROVIDER": "openai",
        "MODEL": "gpt-4o-mini",
        "EMBEDDING_MODEL": "text-embedding-3-large",
        "EMBEDDING_DIM": "3072",
        "OPENAI_API_KEY": "placeholder",
        "VOYAGE_API_KEY": voyage_key,
        "PINECONE_INDEX_NAME": index_name,
        "PINECONE_INDEX_HOST": host,
    }
    return subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=180,
    )


def test_boot_refuses_missionary_index():
    result = _boot("pathway")
    assert result.returncode != 0
    assert "IndexConfigError" in result.stderr


def test_boot_refuses_mismatched_host():
    result = _boot("instructor-assistant", "pathway-a1b2c3d.svc.x.pinecone.io")
    assert result.returncode != 0
    assert "IndexConfigError" in result.stderr


def test_boot_accepts_instructor_index():
    result = _boot("instructor-assistant", HOST)
    assert result.returncode == 0, result.stderr[-2000:]


# --- post-retrieval role assertion ----------------------------------------------


def test_assertion_drops_planted_missionary_node(caplog):
    nodes = [_node(), _node(role="missionary", slug="my-gatherings"), _node(slug="ferpa-ia")]
    with caplog.at_level(logging.ERROR, logger="uvicorn"):
        kept, dropped = assert_instructor_nodes(nodes)

    assert dropped == 1
    assert [n.node.metadata["slug"] for n in kept] == ["pay-dates-ia", "ferpa-ia"]
    assert any("audience_leak" in r.getMessage() and "my-gatherings" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "role,source",
    [
        ("ACM", "instructor-assistant"),
        (None, "instructor-assistant"),
        ("instructor", "pathway"),
        ("instructor", None),
        ("Instructor", "instructor-assistant"),
    ],
)
def test_assertion_drops_wrong_role_or_source(role, source):
    kept, dropped = assert_instructor_nodes([_node(role=role, source=source)])
    assert kept == [] and dropped == 1


def test_assertion_respects_narrowed_sources(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_SOURCES", "instructor-assistant")
    kept, dropped = assert_instructor_nodes([_node(source="instructor-assistant-linked")])
    assert kept == [] and dropped == 1


def test_postprocessor_counts_drops_across_calls():
    guard = AudienceGuardPostprocessor()
    guard.postprocess_nodes([_node(role="missionary")])
    out = guard.postprocess_nodes([_node(), _node(source="pathway")])
    assert len(out) == 1
    assert guard.dropped == 2


def test_chat_engine_runs_the_guard_first(monkeypatch):
    from llama_index.core.llms import MockLLM
    from llama_index.core.settings import Settings

    import app.engine as engine_module

    monkeypatch.setattr(Settings, "_llm", MockLLM(), raising=False)
    index = MagicMock()
    with patch.object(engine_module, "get_index", return_value=index):
        engine = engine_module.get_chat_engine(filters=instructor_filters())

    assert isinstance(engine._node_postprocessors[0], AudienceGuardPostprocessor)
    assert engine.audience_guard is engine._node_postprocessors[0]
    # The retriever was built with the pinned filter.
    assert index.as_retriever.call_args.kwargs["filters"] == instructor_filters()


def _guarded_engine(text: str, dropped: int):
    class _Stream:
        source_nodes: list = []

        async def async_response_gen(self):
            if text:
                yield text

    guard = AudienceGuardPostprocessor()
    guard.dropped = dropped
    engine = MagicMock()
    engine.audience_guard = guard

    async def _astream(*args, **kwargs):
        return _Stream()

    engine.astream_chat = _astream
    return engine


def _run(orchestrator):
    return asyncio.run(orchestrator.run(
        "q", [], filters=None, params=None, timezone="UTC", event_handler=None
    ))


def test_orchestrator_reports_guard_drops():
    from app.engine.retrieval_orchestrator import RetrievalOrchestrator

    orchestrator = RetrievalOrchestrator()
    with patch("app.engine.retrieval_orchestrator.get_chat_engine",
               return_value=_guarded_engine("Answer [^1].", 2)):
        _run(orchestrator)
    assert orchestrator.audience_leak_dropped == 2


def test_orchestrator_reports_guard_drops_even_when_synthesis_fails():
    from app.engine.retrieval_orchestrator import RetrievalOrchestrator, SynthesisFailedError

    orchestrator = RetrievalOrchestrator()
    with patch("app.engine.retrieval_orchestrator.get_chat_engine",
               return_value=_guarded_engine("", 3)):
        with pytest.raises(SynthesisFailedError):
            _run(orchestrator)
    assert orchestrator.audience_leak_dropped == 3


def test_orchestrator_refuses_an_engine_without_its_guard():
    from app.engine.retrieval_orchestrator import RetrievalOrchestrator

    engine = _guarded_engine("Answer [^1].", 0)
    engine.audience_guard = None
    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        with pytest.raises(RuntimeError, match="no audience guard"):
            _run(RetrievalOrchestrator())


# --- health ----------------------------------------------------------------------


def test_readiness_reports_index_and_guard(monkeypatch):
    from app.api.routers import health

    monkeypatch.setattr(health.langfuse, "auth_check", lambda: True)
    store = MagicMock()
    monkeypatch.setattr(health, "get_vector_store", lambda: store)
    body = asyncio.run(health.readiness())
    assert body == {"status": "ok", "index": "instructor-assistant", "guard": "ok"}
    # Data plane, through the request client — not a control-plane describe_index.
    store.client.describe_index_stats.assert_called_once()


def test_readiness_reports_unreachable_data_plane(monkeypatch):
    from app.api.routers import health

    monkeypatch.setattr(health.langfuse, "auth_check", lambda: True)
    store = MagicMock()
    store.client.describe_index_stats.side_effect = TimeoutError("read timed out")
    monkeypatch.setattr(health, "get_vector_store", lambda: store)
    body = asyncio.run(health.readiness())
    assert body["status"] == "degraded" and body["guard"] == "ok"


def test_readiness_skips_pinecone_when_guard_refuses(monkeypatch):
    from app.api.routers import health

    monkeypatch.setenv("PINECONE_INDEX_NAME", "pathway")
    monkeypatch.setattr(health.langfuse, "auth_check", lambda: True)
    get_store = MagicMock()
    monkeypatch.setattr(health, "get_vector_store", get_store)
    body = asyncio.run(health.readiness())

    assert body["guard"] == "error" and body["status"] == "degraded"
    get_store.assert_not_called()  # never touch a refused index


# --- source label ----------------------------------------------------------------


def test_source_label_instructor_guide():
    meta = {"title": "Pay Dates", "source": "instructor-assistant", "url": "https://x.example/pay"}
    assert source_label(meta) == "[Source: Pay Dates — instructor guide]"


def test_source_label_external_page_names_host():
    meta = {
        "title": "AI and Academic Honesty",
        "source": "instructor-assistant-linked",
        "url": "https://www.byui.edu/genai/",
    }
    assert source_label(meta) == "[Source: AI and Academic Honesty — external page from BYU-Idaho (www.byui.edu)]"


def test_module_exposes_no_client_role_input():
    # instructor_filters() takes no arguments: nothing from a request can reach it.
    import inspect

    assert inspect.signature(audience_guard.instructor_filters).parameters == {}


def test_is_instructor_metadata_is_the_guards_rule(monkeypatch):
    assert is_instructor_metadata({"role": "instructor", "source": "instructor-assistant"})
    assert not is_instructor_metadata({"role": "missionary", "source": "instructor-assistant"})
    monkeypatch.setenv("RETRIEVAL_SOURCES", "instructor-assistant")
    assert not is_instructor_metadata({"role": "instructor", "source": "instructor-assistant-linked"})


def test_leak_count_is_live_when_a_disconnect_cancels_the_run():
    """The stream cancels run() and reads the count before run()'s cleanup can
    execute. The count must already be there."""
    from app.engine.retrieval_orchestrator import RetrievalOrchestrator

    guard = AudienceGuardPostprocessor()
    engine = MagicMock()
    engine.audience_guard = guard

    async def _astream(*args, **kwargs):
        guard.dropped = 2  # retrieval ran and the guard dropped two nodes
        await asyncio.sleep(3600)  # synthesis still running when the client leaves

    engine.astream_chat = _astream

    async def scenario():
        orchestrator = RetrievalOrchestrator()
        with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
            task = asyncio.create_task(orchestrator.run(
                "q", [], filters=None, params=None, timezone="UTC", event_handler=None
            ))
            await asyncio.sleep(0.05)
            task.cancel()
            seen_at_cancel = orchestrator.audience_leak_dropped  # what on_stream_end reads
            try:
                await task
            except asyncio.CancelledError:
                pass
        return seen_at_cancel

    assert asyncio.run(scenario()) == 2


def test_readiness_builds_the_store_off_the_event_loop(monkeypatch):
    import threading

    from app.api.routers import health

    monkeypatch.setattr(health.langfuse, "auth_check", lambda: True)
    threads = []

    def _store():
        threads.append(threading.current_thread())
        return MagicMock()

    monkeypatch.setattr(health, "get_vector_store", _store)
    asyncio.run(health.readiness())
    assert threads and threads[0] is not threading.main_thread()


def test_boot_refuses_a_missing_voyage_key():
    result = _boot("instructor-assistant", voyage_key="")
    assert result.returncode != 0
    assert "VOYAGE_API_KEY" in result.stderr


def test_app_engine_imports_without_a_voyage_key():
    # Offline callers (scripts/ask.py's check, tests) import app.engine.login_links.
    result = subprocess.run(
        [sys.executable, "-c", "import app.engine.login_links"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=180,
        env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
    )
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.mark.parametrize("host,owner", [
    ("www.byupathway.edu", "BYU-Pathway"),
    ("resourcecenter.byupathway.org", "BYU-Pathway"),
    ("brightspotcdn.byui.edu", "BYU-Idaho"),
    ("marriott.byu.edu", "BYU"),
    ("community.canvaslms.com", "Canvas"),
    ("faq.whatsapp.com", "WhatsApp"),
    ("notbyui.edu", None),
    ("example.org", None),
])
def test_site_owner_by_domain_suffix(host, owner):
    from app.engine.custom_condense_plus_context import site_owner

    assert site_owner(host) == owner


def test_source_label_unknown_site_keeps_the_host_only():
    meta = {"title": "T", "source": "instructor-assistant-linked", "url": "https://example.org/x"}
    assert source_label(meta) == "[Source: T — external page (example.org)]"
