from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llama_index.core.callbacks import CallbackManager
from llama_index.core.settings import Settings

from app.engine.retrieval_orchestrator import (
    RetrievalOrchestrator,
    SynthesisFailedError,
    _ensure_minimum_citations,
)


class _FakeStream:
    def __init__(self, text: str, source_nodes: list, fail_after: int | None = None):
        self._text = text
        self.source_nodes = source_nodes
        self._fail_after = fail_after

    async def async_response_gen(self):
        for i in range(0, len(self._text), 7):
            if self._fail_after is not None and i >= self._fail_after:
                raise RuntimeError("OpenAI 503")
            yield self._text[i : i + 7]


def _node(url: str, text: str):
    n = MagicMock()
    n.node.metadata = {"url": url}
    n.node.text = text
    n.node.get_content.return_value = text
    n.metadata = {"url": url}
    n.text = text
    return n


def _engine(response):
    engine = MagicMock()
    engine.astream_chat = AsyncMock(return_value=response)
    engine.callback_manager.handlers = []
    return engine


async def _collect(response) -> str:
    return "".join([t async for t in response.async_response_gen()])


@pytest.mark.asyncio
async def test_orchestrator_runs_classic_engine_and_keeps_sources():
    nodes = [_node("https://example.org/guide", "Pay days are the 8th and 23rd.")]
    engine = _engine(_FakeStream("Pay days are the 8th and 23rd [^1].", nodes))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        result = await RetrievalOrchestrator().run(
            "When am I paid?", [], filters=None, params=None, timezone="UTC", event_handler=object()
        )

    engine.astream_chat.assert_awaited_once()
    assert result.source_nodes == nodes
    assert await _collect(result) == "Pay days are the 8th and 23rd [^1]."


@pytest.mark.asyncio
async def test_orchestrator_applies_link_integrity():
    nodes = [_node("https://example.org/guide", "See the guide.")]
    draft = "Use [the form](https://invented.example.com/form) [^1]."
    engine = _engine(_FakeStream(draft, nodes))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        result = await RetrievalOrchestrator().run(
            "q", [], filters=None, params=None, timezone="UTC", event_handler=None
        )

    text = await _collect(result)
    assert "invented.example.com" not in text
    assert "the form" in text


@pytest.mark.asyncio
async def test_orchestrator_ships_draft_when_guards_raise():
    engine = _engine(_FakeStream("Plain answer [^1].", []))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine), \
         patch("app.engine.retrieval_orchestrator.apply_grounding_guards",
               side_effect=RuntimeError("guard broke")):
        result = await RetrievalOrchestrator().run(
            "q", [], filters=None, params=None, timezone="UTC", event_handler=None
        )

    assert await _collect(result) == "Plain answer [^1]."


def test_ensure_minimum_citations_adds_marker_to_uncited_sourced_answer():
    node = MagicMock()
    text = "Pay days depend on country [^2].\nPay days are the 8th and 23rd.\n- Check the pay schedule."

    fixed = _ensure_minimum_citations(text, [node])

    assert "Pay days are the 8th and 23rd. [^1]" in fixed
    assert "- Check the pay schedule. [^1]" in fixed


def test_ensure_minimum_citations_leaves_already_cited_answer_alone():
    node = MagicMock()
    text = "Pay days are the 8th and 23rd [^2]."

    assert _ensure_minimum_citations(text, [node]) == text


@pytest.mark.asyncio
async def test_event_handler_is_scoped_to_the_request_not_global(monkeypatch):
    global_handler = object()
    monkeypatch.setattr(Settings, "_callback_manager", CallbackManager([global_handler]), raising=False)
    engine = _engine(_FakeStream("Answer [^1].", [_node("https://x.example", "t")]))
    event_handler = MagicMock()

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        await RetrievalOrchestrator().run(
            "q", [], filters=None, params=None, timezone="UTC", event_handler=event_handler
        )

    # The process-wide manager is untouched; the request got its own.
    assert Settings.callback_manager.handlers == [global_handler]
    assert engine.callback_manager.handlers == [global_handler, event_handler]
    assert engine._retriever.callback_manager is engine.callback_manager


@pytest.mark.asyncio
async def test_failed_stream_raises_instead_of_shipping_blank_answer():
    engine = _engine(_FakeStream("", [_node("https://x.example", "t")], fail_after=0))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        with pytest.raises(SynthesisFailedError):
            await RetrievalOrchestrator().run(
                "q", [], filters=None, params=None, timezone="UTC", event_handler=None
            )


@pytest.mark.asyncio
async def test_stream_that_fails_midway_raises_instead_of_shipping_truncated_answer():
    text = "The first part of a long answer that is cut off by an upstream error [^1]."
    engine = _engine(_FakeStream(text, [_node("https://x.example", "t")], fail_after=14))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        with pytest.raises(SynthesisFailedError):
            await RetrievalOrchestrator().run(
                "q", [], filters=None, params=None, timezone="UTC", event_handler=None
            )


@pytest.mark.asyncio
async def test_empty_answer_raises():
    engine = _engine(_FakeStream("   ", [_node("https://x.example", "t")]))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        with pytest.raises(SynthesisFailedError):
            await RetrievalOrchestrator().run(
                "q", [], filters=None, params=None, timezone="UTC", event_handler=None
            )


@pytest.mark.asyncio
async def test_draft_fence_survives_guards_and_its_citations_are_hoisted():
    draft = (
        "Here is a welcome message based on the guide [^1].\n\n"
        "```message\nHi [Student Name], welcome to [Course]! [^2]\n```"
    )
    nodes = [_node("https://x.example/a", "a"), _node("https://x.example/b", "b")]
    engine = _engine(_FakeStream(draft, nodes))

    with patch("app.engine.retrieval_orchestrator.get_chat_engine", return_value=engine):
        result = await RetrievalOrchestrator().run(
            "q", [], filters=None, params=None, timezone="UTC", event_handler=None
        )

    text = await _collect(result)
    assert "```message\nHi [Student Name], welcome to [Course]!\n```\n\n[^2]" in text
    assert "based on the guide [^1]." in text
