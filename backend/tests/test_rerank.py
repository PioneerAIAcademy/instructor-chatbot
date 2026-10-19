"""The shared rerank rules (`rerank_nodes`), used by both engine paths and by
scripts/retrieve.py, so the script and the Phase 2 eval can't drift from
production."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.engine import custom_condense_plus_context as ccpc
from app.engine.audience_guard import AudienceGuardPostprocessor
from app.engine.custom_condense_plus_context import (
    RERANK_MIN_SCORE,
    RERANK_MODEL,
    RERANK_TOP_K,
    rerank_nodes,
)


def _node(text: str, score: float = 0.5, url: str = "https://x.example/a", seq: int = 1):
    meta = {"url": url, "sequence": seq, "role": "instructor", "source": "instructor-assistant", "slug": text}
    return NodeWithScore(node=TextNode(text=text, id_=f"{text}#1", metadata=meta), score=score)


class _FakeVoyage:
    """Stands in for `vo`: scores each document from a table."""

    def __init__(self, scores=None, error: Exception | None = None):
        self.scores = scores or {}
        self.error = error
        self.calls = []

    def rerank(self, query, documents, model, top_k):
        self.calls.append({"documents": list(documents), "model": model, "top_k": top_k})
        if self.error:
            raise self.error
        ranked = sorted(documents, key=lambda d: self.scores.get(d, 0.0), reverse=True)[:top_k]
        return SimpleNamespace(results=[
            SimpleNamespace(document=d, relevance_score=self.scores.get(d, 0.0)) for d in ranked
        ])


@pytest.fixture
def voyage(monkeypatch):
    fake = _FakeVoyage()
    monkeypatch.setattr(ccpc, "vo", fake)
    return fake


def test_two_or_more_texts_rerank_with_cutoff(voyage):
    voyage.scores = {"a": 0.9, "b": RERANK_MIN_SCORE - 0.01, "c": 0.5}
    out = rerank_nodes([_node("a"), _node("b"), _node("c")], "q")

    assert out.attempted and out.success
    assert [n.text for n in out.nodes] == ["a", "c"]  # best first, "b" below the cutoff
    assert out.nodes[0].node.metadata["rerank_relevance"] == 0.9
    assert voyage.calls[0]["model"] == RERANK_MODEL and voyage.calls[0]["top_k"] == RERANK_TOP_K


def test_duplicate_texts_are_ranked_once(voyage):
    voyage.scores = {"a": 0.9, "b": 0.8}
    rerank_nodes([_node("a"), _node("a"), _node("b")], "q")
    assert voyage.calls[0]["documents"] == ["a", "b"]


def test_one_unique_text_skips_rerank_and_cutoff(voyage):
    out = rerank_nodes([_node("only", score=0.1), _node("only", score=0.1)], "q")

    assert not out.attempted
    assert voyage.calls == []
    assert [n.text for n in out.nodes] == ["only"]  # kept, though 0.1 < cutoff
    assert out.nodes[0].node.metadata["rerank_relevance"] == 0.1


def test_no_nodes_makes_no_call(voyage):
    out = rerank_nodes([], "q")
    assert out.nodes == [] and not out.attempted and voyage.calls == []


def test_voyage_failure_keeps_every_text_unranked_in_retrieval_order(voyage, monkeypatch):
    monkeypatch.setattr(ccpc.time, "sleep", lambda _s: None)  # skip the retry backoff
    voyage.error = RuntimeError("Voyage 503")
    out = rerank_nodes([_node("c"), _node("a"), _node("b")], "q")

    assert out.attempted and not out.success and isinstance(out.error, RuntimeError)
    assert [n.text for n in out.nodes] == ["c", "a", "b"]
    assert len(voyage.calls) == 3  # retried


def _engine_shell():
    engine = ccpc.CustomCondensePlusContextChatEngine.__new__(ccpc.CustomCondensePlusContextChatEngine)
    engine.callback_manager = MagicMock()
    return engine


@pytest.mark.parametrize("use_async", [False, True])
def test_engine_paths_use_the_shared_rules(voyage, use_async):
    voyage.scores = {"a": 0.9, "b": 0.05}
    nodes = [_node("a", url="https://x.example/1"), _node("b", url="https://x.example/2")]
    engine = _engine_shell()

    if use_async:
        organized = asyncio.run(engine._aorganize_nodes(nodes, message="q"))
    else:
        organized = engine._organize_nodes(nodes, message="q")

    assert [n.text for n in organized] == ["a"]
    engine.callback_manager.on_event_start.assert_called_once()
    engine.callback_manager.on_event_end.assert_called_once()


def test_engine_emits_no_rerank_event_when_skipped(voyage):
    engine = _engine_shell()
    engine._organize_nodes([_node("only")], message="q")
    engine.callback_manager.on_event_start.assert_not_called()


def test_engine_merges_a_page_in_sequence_order(voyage):
    voyage.scores = {"part 2": 0.9, "part 1": 0.8}
    nodes = [_node("part 2", seq=2), _node("part 1", seq=1)]
    organized = _engine_shell()._organize_nodes(nodes, message="q")
    assert len(organized) == 1
    assert organized[0].node.text == "part 1\n\npart 2"


# --- scripts/retrieve.py -----------------------------------------------------------


def _load_retrieve_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "retrieve.py"
    spec = importlib.util.spec_from_file_location("retrieve_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("raw", [[], [_node("missionary", score=0.9)]])
def test_retrieve_script_handles_nothing_left_to_rank(voyage, monkeypatch, raw):
    """Empty retrieval, or the guard dropping everything, must report, not crash."""
    if raw:
        raw[0].node.metadata["role"] = "missionary"
    guard = AudienceGuardPostprocessor()
    engine = MagicMock()
    engine._retriever.retrieve.return_value = raw
    engine._node_postprocessors = [guard]
    engine.audience_guard = guard

    script = _load_retrieve_script()
    with patch("app.engine.get_chat_engine", return_value=engine), \
         patch("app.settings.init_settings"), \
         patch("app.engine.audience_guard.check_index_config", return_value="instructor-assistant"):
        result = script.run_retrieval("q")
        prepared = script.run_retrieval("q", "instructor-assistant")  # setup skipped

    assert result["reranked"] == []
    assert result["rerank_attempted"] is False
    assert result["dropped"] == len(raw)
    assert prepared["index"] == "instructor-assistant"
    assert voyage.calls == []


def test_a_missing_voyage_key_fails_at_once_without_retry_sleeps(monkeypatch):
    sleeps = []
    monkeypatch.setattr(ccpc, "vo", None)
    monkeypatch.setattr(ccpc.time, "sleep", lambda s: sleeps.append(s))

    class _NoKey:
        @staticmethod
        def Client():
            raise RuntimeError("No API key provided")

    monkeypatch.setattr(ccpc, "voyageai", _NoKey)
    out = rerank_nodes([_node("a"), _node("b")], "q")
    assert out.attempted and not out.success and "No API key" in str(out.error)
    assert sleeps == []  # no 2 x 5 s of retry backoff
