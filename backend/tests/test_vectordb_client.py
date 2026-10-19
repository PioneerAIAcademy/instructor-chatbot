"""Tests for the shared, bounded Pinecone client (app/engine/vectordb.py).

Why these exist (2026-07-26): get_vector_store() used to build a fresh
PineconeVectorStore per retrieval (2-3x per turn), so no urllib3 connection or
TLS session was ever reused; and pinecone-client 5.0.1 passes timeout=None to
urllib3 explicitly, so a stalled read owned the event loop indefinitely
(measured 157-327 s stalls vs an 11.5 s healthy maximum). These tests pin BOTH
halves of the fix and — most importantly — pin that the bound cannot change
what retrieval returns.

No network, no API keys: pinecone.Pinecone is patched, so no host resolution and
no HTTP ever happens.
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest

from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.core.vector_stores.utils import node_to_metadata_dict


_PINECONE_ENV = {
    "PINECONE_API_KEY": "test-key",
    "PINECONE_INDEX_NAME": "instructor-assistant",
    "PINECONE_ENVIRONMENT": "us-east-1",
}


def _reload_vectordb(**overrides):
    """Reload the module so its import-time tunables re-read the env.

    NOTE: app/engine/index.py binds get_vector_store at import time, so tests
    must call the function off the RELOADED module, never app.engine.index's
    copy.
    """
    env = dict(_PINECONE_ENV)
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        from app.engine import vectordb

        importlib.reload(vectordb)
    return vectordb


@pytest.fixture
def pinecone_env():
    with patch.dict(os.environ, _PINECONE_ENV, clear=False):
        yield


@pytest.fixture
def fake_pinecone():
    """Patch pinecone.Pinecone; expose the class mock and the Index mock."""
    fake_index = MagicMock(name="pinecone_index")
    client = MagicMock(name="pinecone_client")
    client.Index.return_value = fake_index
    client.openapi_config = MagicMock(name="openapi_config")
    with patch("pinecone.Pinecone", return_value=client) as cls:
        yield cls, client, fake_index


# What a match carries when Pinecone is asked for the embedding. Short here; in
# production this is a 3072-float vector, which is the whole point of #111.
_VENDOR_VALUES = [0.1, 0.2, 0.3]


def _match(node: TextNode, score: float, values=_VENDOR_VALUES):
    m = MagicMock()
    m.id = node.node_id
    m.score = score
    # values=None models a real include_values=False reply: pinecone's generated
    # model resolves a missing attribute through __getattr__ -> self.get(attr),
    # which defaults to None instead of raising.
    m.values = values
    m.metadata = node_to_metadata_dict(node, remove_text=False, flat_metadata=False)
    return m


# ---------------------------------------------------------------------------
# 1. The store (and therefore the urllib3 pool) is built once and reused
# ---------------------------------------------------------------------------


def test_vector_store_is_built_once_across_many_retrievals(pinecone_env, fake_pinecone):
    cls, client, _ = fake_pinecone
    vectordb = _reload_vectordb()

    stores = [vectordb.get_vector_store() for _ in range(5)]

    assert cls.call_count == 1, "a new Pinecone client per retrieval = a new TLS handshake"
    assert client.Index.call_count == 1
    assert all(s is stores[0] for s in stores)


def test_reset_cache_forces_a_rebuild(pinecone_env, fake_pinecone):
    cls, _, _ = fake_pinecone
    vectordb = _reload_vectordb()

    first = vectordb.get_vector_store()
    vectordb.reset_vector_store_cache()
    second = vectordb.get_vector_store()

    assert first is not second
    assert cls.call_count == 2


def test_changing_the_index_name_invalidates_the_cache(pinecone_env, fake_pinecone):
    cls, _, _ = fake_pinecone
    vectordb = _reload_vectordb()

    first = vectordb.get_vector_store()
    # The second name must be allow-listed: the index guard refuses any other.
    staging = {
        "PINECONE_INDEX_NAME": "instructor-assistant-staging",
        "ALLOWED_INDEX_NAMES": "instructor-assistant,instructor-assistant-staging",
    }
    with patch.dict(os.environ, staging, clear=False):
        second = vectordb.get_vector_store()

    assert first is not second
    assert second.index_name == "instructor-assistant-staging"
    assert cls.call_count == 2


def test_cache_can_be_disabled(pinecone_env, fake_pinecone):
    cls, _, _ = fake_pinecone
    vectordb = _reload_vectordb(PINECONE_STORE_CACHE_ENABLED="false")

    a = vectordb.get_vector_store()
    b = vectordb.get_vector_store()

    assert a is not b
    assert cls.call_count == 2


def test_missing_credentials_still_raise_the_same_valueerror(fake_pinecone):
    vectordb = _reload_vectordb()
    with patch.dict(os.environ, {"PINECONE_API_KEY": ""}, clear=False):
        with pytest.raises(ValueError, match="PINECONE_API_KEY"):
            vectordb.get_vector_store()


# ---------------------------------------------------------------------------
# 2. The client is bounded: per-read timeout, pool size, retry policy
# ---------------------------------------------------------------------------


def test_defaults_are_the_documented_values(pinecone_env, fake_pinecone):
    vectordb = _reload_vectordb()
    with patch.dict(os.environ, {}, clear=True):
        importlib.reload(vectordb)
    assert vectordb.PINECONE_REQUEST_TIMEOUT_SECONDS == pytest.approx(12.0)
    assert vectordb.PINECONE_POOL_MAXSIZE == 20
    assert vectordb.PINECONE_STORE_CACHE_ENABLED is True
    assert vectordb.PINECONE_INCLUDE_VALUES_ENABLED is False


def test_read_timeout_reaches_the_pinecone_query_call(pinecone_env, fake_pinecone):
    _, _, fake_index = fake_pinecone
    fake_index.query.return_value = MagicMock(matches=[])
    vectordb = _reload_vectordb(PINECONE_REQUEST_TIMEOUT_SECONDS="20")

    store = vectordb.get_vector_store()
    store.query(VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3))

    assert fake_index.query.call_args.kwargs["_request_timeout"] == pytest.approx(20.0)


def test_env_override_changes_the_bound(pinecone_env, fake_pinecone):
    _, _, fake_index = fake_pinecone
    fake_index.query.return_value = MagicMock(matches=[])
    vectordb = _reload_vectordb(PINECONE_REQUEST_TIMEOUT_SECONDS="7.5")

    vectordb.get_vector_store().query(
        VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3)
    )

    assert fake_index.query.call_args.kwargs["_request_timeout"] == pytest.approx(7.5)


def test_zero_disables_the_bound(pinecone_env, fake_pinecone):
    """Escape hatch: 0 restores the pre-fix unbounded behaviour."""
    _, _, fake_index = fake_pinecone
    fake_index.query.return_value = MagicMock(matches=[])
    vectordb = _reload_vectordb(PINECONE_REQUEST_TIMEOUT_SECONDS="0")

    vectordb.get_vector_store().query(
        VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3)
    )

    assert "_request_timeout" not in fake_index.query.call_args.kwargs


def test_a_caller_supplied_timeout_wins(pinecone_env, fake_pinecone):
    _, _, fake_index = fake_pinecone
    fake_index.query.return_value = MagicMock(matches=[])
    vectordb = _reload_vectordb()

    vectordb.get_vector_store().query(
        VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3),
        _request_timeout=3.0,
    )

    assert fake_index.query.call_args.kwargs["_request_timeout"] == pytest.approx(3.0)


def test_describe_index_stats_is_bounded_too(pinecone_env, fake_pinecone):
    """Reached by the vendor store when a query carries no embedding."""
    _, _, fake_index = fake_pinecone
    vectordb = _reload_vectordb()

    vectordb.get_vector_store().client.describe_index_stats()

    assert fake_index.describe_index_stats.call_args.kwargs[
        "_request_timeout"
    ] == pytest.approx(12.0)


def test_writes_are_left_at_vendor_defaults(pinecone_env, fake_pinecone):
    """Upserts are legitimately slow; the read bound must not touch them."""
    _, _, fake_index = fake_pinecone
    vectordb = _reload_vectordb()

    vectordb.get_vector_store().client.upsert([{"id": "a", "values": [0.0]}])

    assert "_request_timeout" not in fake_index.upsert.call_args.kwargs


def test_pool_size_and_retries_are_pinned_on_the_shared_client(
    pinecone_env, fake_pinecone
):
    _, client, _ = fake_pinecone
    vectordb = _reload_vectordb(PINECONE_POOL_MAXSIZE="12")

    vectordb.get_vector_store()

    assert client.openapi_config.connection_pool_maxsize == 12
    retries = client.openapi_config.retries
    assert retries.total == 1 and retries.connect == 1
    # POST /query was never read-retryable; pinning it removes the hidden
    # timeout multiplier from urllib3's default Retry(3).
    assert retries.read is False


def test_a_fired_bound_is_logged_and_reraised(pinecone_env, fake_pinecone, caplog):
    """An armed timeout must never be silent — upstream swallows it into an
    empty tray, so the log line is the only evidence it happened."""
    from urllib3.exceptions import ReadTimeoutError

    _, _, fake_index = fake_pinecone
    fake_index.query.side_effect = ReadTimeoutError(None, "https://x", "Read timed out.")
    vectordb = _reload_vectordb()
    store = vectordb.get_vector_store()

    with caplog.at_level("ERROR", logger="uvicorn"):
        with pytest.raises(ReadTimeoutError):
            store.query(VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3))

    assert any(
        "exceeded the 12.0s bound" in r.getMessage() for r in caplog.records
    ), caplog.text


def test_unrelated_errors_are_not_logged_as_timeouts(pinecone_env, fake_pinecone, caplog):
    _, _, fake_index = fake_pinecone
    fake_index.query.side_effect = RuntimeError("boom")
    vectordb = _reload_vectordb()
    store = vectordb.get_vector_store()

    with caplog.at_level("ERROR", logger="uvicorn"):
        with pytest.raises(RuntimeError):
            store.query(VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3))

    assert not any("exceeded the" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 3. ACCURACY: results and the request payload are unchanged
# ---------------------------------------------------------------------------


def _query_once(
    vectordb, fake_index, nodes_and_scores, values=_VENDOR_VALUES, **query_kwargs
):
    fake_index.reset_mock()
    fake_index.query.return_value = MagicMock(
        matches=[_match(n, s, values=values) for n, s in nodes_and_scores]
    )
    store = vectordb.get_vector_store()
    result = store.query(
        VectorStoreQuery(query_embedding=[0.25] * 8, similarity_top_k=2),
        **query_kwargs,
    )
    payload = dict(fake_index.query.call_args.kwargs)
    # Drop BOTH of this module's injections, so what remains is the request the
    # vendor store built. Each is pinned by its own test: the bound by
    # test_read_timeout_reaches_the_pinecone_query_call, the projection by
    # test_values_are_excluded_from_every_read_by_default.
    payload.pop("_request_timeout", None)
    payload.pop("include_values", None)
    return result, payload


def test_the_bound_changes_neither_the_request_nor_the_results(
    pinecone_env, fake_pinecone
):
    """The load-bearing accuracy test — for the BOUND specifically.

    `_request_timeout` is an OpenAPI *endpoint* parameter: pinecone/data/index.py
    excludes _OPENAPI_ENDPOINT_PARAMS from the QueryRequest body and passes them
    separately, so the bound cannot reach Pinecone's ranking. Pin that: same
    request payload, same ids, same scores, same node text, bound on vs off.

    Scope note: `_query_once` also drops `include_values`, so this test says
    nothing about it. That is deliberate — it is a QueryRequest *body* field, not
    an endpoint parameter, so "the body is unchanged" is simply not the claim
    there. Its own claim (a response projection cannot move ids, scores or text)
    is pinned by test_excluding_values_changes_neither_ids_scores_nor_text.
    """
    _, _, fake_index = fake_pinecone
    nodes = [
        (TextNode(text="Block 3 begins May 4.", id_="n1"), 0.91),
        (TextNode(text="Tuition is $89 per credit.", id_="n2"), 0.77),
    ]

    bounded = _reload_vectordb(PINECONE_REQUEST_TIMEOUT_SECONDS="20")
    bounded_result, bounded_payload = _query_once(bounded, fake_index, nodes)

    unbounded = _reload_vectordb(PINECONE_REQUEST_TIMEOUT_SECONDS="0")
    unbounded_result, unbounded_payload = _query_once(unbounded, fake_index, nodes)

    assert bounded_payload == unbounded_payload
    assert bounded_result.ids == unbounded_result.ids == ["n1", "n2"]
    assert bounded_result.similarities == unbounded_result.similarities == [0.91, 0.77]
    assert [n.get_content() for n in bounded_result.nodes] == [
        n.get_content() for n in unbounded_result.nodes
    ]


def test_reuse_changes_neither_the_request_nor_the_results(pinecone_env, fake_pinecone):
    """A cached store must answer identically to a freshly built one."""
    _, _, fake_index = fake_pinecone
    nodes = [(TextNode(text="EnglishConnect 3 is $35.60 per course.", id_="n1"), 0.88)]

    cached = _reload_vectordb(PINECONE_STORE_CACHE_ENABLED="true")
    cached.get_vector_store()  # warm it, so the second call is the cached one
    cached_result, cached_payload = _query_once(cached, fake_index, nodes)

    fresh = _reload_vectordb(PINECONE_STORE_CACHE_ENABLED="false")
    fresh_result, fresh_payload = _query_once(fresh, fake_index, nodes)

    assert cached_payload == fresh_payload
    assert cached_result.ids == fresh_result.ids == ["n1"]
    assert cached_result.similarities == fresh_result.similarities == [0.88]
    assert cached_result.nodes[0].get_content() == fresh_result.nodes[0].get_content()


def test_store_identity_matches_the_vendor_construction(pinecone_env, fake_pinecone):
    """The store still carries the same api_key/index_name/environment/text_key
    the old three-kwarg construction produced — only the transport changed."""
    _, _, fake_index = fake_pinecone
    vectordb = _reload_vectordb()

    store = vectordb.get_vector_store()

    assert store.api_key == "test-key"
    assert store.index_name == "instructor-assistant"
    assert store.environment == "us-east-1"
    assert store.text_key == "text"
    assert store.stores_text is True
    assert store.is_embedding_query is True
    assert store.namespace is None
    assert store.client._index is fake_index


def test_index_host_when_set_skips_the_control_plane_lookup(pinecone_env, fake_pinecone):
    """Pinning the host removes a control-plane round trip from store creation.

    pc.Index(name) must first call describe_index on api.pinecone.io to discover
    the data-plane host. That call is NOT covered by the read bound (which wraps
    query/fetch/describe_index_stats on the data plane) and has no timeout of its
    own — measured 2026-07-26, it blocked store construction for 540s on the
    event loop while the data plane was answering in 1-2s, and the turn ended in
    a stream hiccup. With the host pinned, a control-plane outage stops being a
    serving outage.
    """
    _, fake_pc, _ = fake_pinecone
    vectordb = _reload_vectordb(PINECONE_INDEX_HOST="instructor-assistant-abc123.svc.test.pinecone.io")

    vectordb.get_vector_store()

    fake_pc.Index.assert_called_once_with(host="instructor-assistant-abc123.svc.test.pinecone.io")


def test_index_name_lookup_is_the_fallback_when_host_is_unset(pinecone_env, fake_pinecone):
    """Unset host keeps today's behaviour, so this is safe to ship un-configured."""
    _, fake_pc, _ = fake_pinecone
    vectordb = _reload_vectordb(PINECONE_INDEX_HOST="")

    vectordb.get_vector_store()

    assert fake_pc.Index.call_args.kwargs.get("host") is None
    assert fake_pc.Index.call_args.args == ("instructor-assistant",)


# ---------------------------------------------------------------------------
# 5. EGRESS: the embedding projection is off (#111)
#
# The vendor store asks for every match's full embedding and assigns it to
# node.embedding, which nothing in this codebase reads. Pinecone meters read
# egress in RESPONSE BYTES, so at dimension=3072 that was ~16x the payload we
# need, and PROD exhausted the 1 GB monthly allowance on 2026-08-17 (429,
# code 8). These pin that the projection is off and that turning it off cannot
# change what retrieval returns.
# ---------------------------------------------------------------------------


def test_values_are_excluded_from_every_read_by_default(pinecone_env, fake_pinecone):
    """The whole fix, in one assertion: no vectors on the wire, unconfigured."""
    _, _, fake_index = fake_pinecone
    vectordb = _reload_vectordb()
    store = vectordb.get_vector_store()

    store.query(VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3))

    assert fake_index.query.call_args.kwargs["include_values"] is False


def test_the_env_escape_hatch_restores_the_vendor_default(pinecone_env, fake_pinecone):
    """PINECONE_INCLUDE_VALUES_ENABLED=true must hand the call back to the vendor.

    Not merely "not False" — the vendor's own True has to survive untouched, so
    the escape hatch is a real rollback and not a third behaviour.
    """
    _, _, fake_index = fake_pinecone
    vectordb = _reload_vectordb(PINECONE_INCLUDE_VALUES_ENABLED="true")
    store = vectordb.get_vector_store()

    store.query(VectorStoreQuery(query_embedding=[0.1] * 8, similarity_top_k=3))

    assert fake_index.query.call_args.kwargs["include_values"] is True


def test_a_match_without_values_still_yields_a_complete_node(pinecone_env, fake_pinecone):
    """The one real risk in #111, pinned.

    With values excluded, the vendor still runs `node.embedding = match.values`
    inside a try/except whose except falls back to legacy_metadata_dict_to_node —
    a path that silently drops start_char_idx and relationships from EVERY node.
    match.values being None (not an error) is what keeps us out of it.

    start_char_idx is the discriminator: metadata_dict_to_node restores it from
    the node's own metadata, while the legacy branch reads node_info.get("start")
    from a dict that has no such key and yields None. So asserting it survived
    proves which branch ran.
    """
    _, _, fake_index = fake_pinecone
    node = TextNode(text="Block 3 begins May 4.", id_="n1", start_char_idx=7, end_char_idx=28)
    vectordb = _reload_vectordb()

    result, _ = _query_once(vectordb, fake_index, [(node, 0.91)], values=None)

    assert result.ids == ["n1"]
    assert result.similarities == [0.91]
    assert result.nodes[0].get_content() == "Block 3 begins May 4."
    assert result.nodes[0].embedding is None
    # Did NOT fall through to the legacy branch:
    assert result.nodes[0].start_char_idx == 7
    assert result.nodes[0].end_char_idx == 28


def test_excluding_values_changes_neither_ids_scores_nor_text(pinecone_env, fake_pinecone):
    """include_values is a response PROJECTION, not a matching parameter.

    Unlike the bound it does travel in the QueryRequest body, so "same payload"
    is not the available argument. The claim is narrower and this is it: what
    Pinecone selects into the reply cannot move which vectors matched, their
    order, or their scores. Projection off vs on, everything user-visible equal.
    """
    _, _, fake_index = fake_pinecone
    nodes = [
        (TextNode(text="Block 3 begins May 4.", id_="n1"), 0.91),
        (TextNode(text="Tuition is $89 per credit.", id_="n2"), 0.77),
    ]

    # Off: Pinecone omits values, so matches carry None.
    off = _reload_vectordb()
    off_result, _ = _query_once(off, fake_index, nodes, values=None)

    # On: the vendor default, matches carry the vector.
    on = _reload_vectordb(PINECONE_INCLUDE_VALUES_ENABLED="true")
    on_result, _ = _query_once(on, fake_index, nodes)

    assert off_result.ids == on_result.ids == ["n1", "n2"]
    assert off_result.similarities == on_result.similarities == [0.91, 0.77]
    assert [n.get_content() for n in off_result.nodes] == [
        n.get_content() for n in on_result.nodes
    ]
    # The only difference is the payload we stopped paying for.
    assert [n.embedding for n in off_result.nodes] == [None, None]
    assert [n.embedding for n in on_result.nodes] == [_VENDOR_VALUES, _VENDOR_VALUES]
