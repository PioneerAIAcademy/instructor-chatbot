"""Pinecone vector store: one bounded client, reused for the process.

WHY THIS FILE IS NOT FIVE LINES (2026-07-26)
--------------------------------------------
1. REUSE. ``get_vector_store()`` used to build a fresh ``PineconeVectorStore`` on
   every retrieval — 2-3x per chat turn (measured: 20 constructions across 10
   requests in bench/server_perf_covenant.log). Each store builds its own
   ``pinecone.Pinecone`` client -> its own ``Index`` -> its own
   ``urllib3.PoolManager``, so no connection and no TLS session was ever reused:
   every retrieval paid a fresh TCP+TLS handshake (measured from this box to the
   Pinecone data plane: 616-911 ms, median ~660 ms), i.e. roughly 1.3-2.0 s per
   turn thrown away. Nothing per-request reaches store construction —
   ``get_index(params)`` never reads ``params`` and ``get_vector_store()`` takes
   no arguments — and per-request ``filters`` bind to the RETRIEVER, not the
   store. So one store per (api key, index, environment) is safe.

2. BOUNDS. ``llama-index-vector-stores-pinecone`` 0.1.9 implements no ``aquery``,
   so ``await retriever.aretrieve(...)`` falls through to llama-index's base stub
   (``llama_index/core/vector_stores/types.py`` -> ``return self.query(...)``) and
   runs a SYNCHRONOUS urllib3 call on the event-loop thread. ``pinecone-client``
   5.0.1 then passes ``timeout=None`` EXPLICITLY to urllib3, which overrides any
   pool default with "wait forever" — verified: ``Configuration`` has no
   ``timeout`` field at all. So a stalled socket owns the whole event loop and
   every asyncio timeout in the process is disarmed, because ``wait_for`` needs a
   loop timer callback to fire.

   Measured 2026-07-26: retrieval spans of 157 / 214 / 240 / 250 / 257 / 327 s
   against a healthy maximum of 11.5 s (median 9.8 s) — a 13x empty gap. During
   one stall an unrelated ``GET /api/v1/chat/config`` was starved for 148.7 s,
   and a 180 s stream watchdog fired at 256.6 s, 52 ms after the blocking call
   finally released. Users saw "I hit a service hiccup".

   The ONLY bound this pinned client honours is the per-request
   ``_request_timeout`` OpenAPI parameter, so it is injected at the one seam every
   read crosses (``_BoundedPineconeIndex``).

3. EGRESS. ``PineconeVectorStore.query`` asks for the full embedding of every
   match (``include_values=True``, hard-coded in
   ``llama-index-vector-stores-pinecone`` 0.1.3 and popped with a ``True``
   default in 0.1.9), and assigns it to ``node.embedding`` — which NOTHING in
   this codebase reads (the only ``.embedding`` reads are OpenAI API responses
   in ``engine/pushback.py``). Pinecone meters read egress in RESPONSE BYTES, so
   at ``dimension=3072`` we paid ~94% waste on every retrieval and PROD hit the
   1 GB monthly cap on 2026-08-17: every query returned 429 ``code 8``. So the
   projection is turned off at the same seam (``_BoundedPineconeIndex.query``).

WHAT THIS CANNOT CHANGE — TWO DIFFERENT SEAMS, SAME CONCLUSION.

``_request_timeout`` never reaches the request body at all. It is an OpenAPI
*endpoint* parameter: ``pinecone/data/index.py`` builds the ``QueryRequest`` body
from the kwargs NOT in ``_OPENAPI_ENDPOINT_PARAMS`` and passes the endpoint params
separately. The body is byte-identical with the bound off, at a tuple, and at a
scalar.

``include_values`` DOES travel in the ``QueryRequest`` body, so the body is not
byte-identical any more — but it is a RESPONSE PROJECTION, not a matching
parameter. It selects which fields Pinecone puts in the reply; it has no say in
which vectors match, their order, or their scores. Nor can it push llama-index
into its deprecated legacy-node branch: with values excluded ``match.values`` is
``None`` rather than an error (pinecone's generated model resolves attributes via
``__getattr__`` -> ``self.get(attr)``, default ``None``), so the vendor's
``node.embedding = match.values`` assigns ``None`` inside its own ``try:`` and
``metadata_dict_to_node`` still builds the node — keeping ``start_char_idx`` and
relationships, which the legacy branch would have silently dropped.

Retrieval results, ranking and the citation tray are untouched by design, and
``tests/test_vectordb_client.py`` pins exactly that for both seams.
"""

import logging
import os
import threading
import time
from typing import Any, Optional, Tuple

from llama_index.vector_stores.pinecone import PineconeVectorStore

logger = logging.getLogger("uvicorn")


# Wall-clock bound (seconds) on ONE Pinecone read ATTEMPT. This is per-attempt,
# not per-call: rest.py turns a scalar into urllib3.Timeout(total=X) and hands it
# to pool_manager.request(), and urllib3 gives every retry a fresh budget.
#
# MEASURED, not assumed. A first attempt at 20 s produced MaxRetryError after
# 182 s (bench/server_final.log) — i.e. ~9 attempts, because the retry policy
# below bounds one layer while the pool manager and the connection pool each
# apply their own. 182 s clears the 180 s stream watchdog, so the user still got
# a hiccup: the first cut of this bound did not actually fix the symptom.
#
# 12 s with the tightened retry policy: healthy reads are 1.1-2.2 s measured to
# the data plane from here and 3.5-5.5 s on the slowest box (2026-07-10 heartbeat
# probe), so this keeps 2-5x headroom, and even at the observed 9x multiplier the
# worst case is ~108 s — comfortably inside the 180 s watchdog, which is the
# number that has to hold. Set 0 to restore the old unbounded behaviour (a hung
# socket then owns the event loop again).
PINECONE_REQUEST_TIMEOUT_SECONDS: float = float(
    os.environ.get("PINECONE_REQUEST_TIMEOUT_SECONDS", "12") or "12"
)

# urllib3 connections kept warm per host. The vendor default is cpu_count() * 5 —
# only 5 on a 1-vCPU Render instance, which never mattered while every retrieval
# had its own pool but does now that one pool serves the whole process (the
# sub-agent runs several retrievals per turn). Above this ceiling urllib3 opens
# and DISCARDS extra connections, which is exactly the handshake cost this cache
# exists to remove.
PINECONE_POOL_MAXSIZE: int = int(os.environ.get("PINECONE_POOL_MAXSIZE", "20") or "20")

# Kill switch for the reuse. "false" restores a fresh store per call (still
# bounded). Keep it on — reuse is the latency win.
PINECONE_STORE_CACHE_ENABLED: bool = (
    os.environ.get("PINECONE_STORE_CACHE_ENABLED", "true").lower() == "true"
)

# Ask Pinecone to include each match's raw embedding in the response. The vendor
# store always asks for them; nothing here ever reads them.
#
# Pinecone meters read egress in RESPONSE BYTES, and at dimension=3072 a
# JSON-encoded embedding is ~32-64 KB per match against ~2.6 KB of metadata —
# so the vectors are ~94% of every reply and pure waste. MEASURED against a live
# dim-3072 index, response bytes with values on vs off:
#
#   topK    on bytes   off bytes   ratio
#      1      45,586        3,197   14.3x
#      8     361,407       22,524   16.0x
#     35   1,576,071       94,059   16.8x   <- our retriever default
#    100   4,506,163      271,135   16.6x   <- supervisor section-diverse fetch
#
# On 2026-08-17 PROD exhausted Pinecone's 1 GB monthly read-egress allowance and
# every retrieval began returning 429 (`{"code":8,...}`). This default is what
# keeps that from recurring; it does not refund a spent billing period.
#
# Set "true" to restore the vendor default if a caller ever genuinely needs the
# vectors back — then expect the ~16x payload, and size the plan for it.
PINECONE_INCLUDE_VALUES_ENABLED: bool = (
    os.environ.get("PINECONE_INCLUDE_VALUES_ENABLED", "false").lower() == "true"
)

# The index's data-plane host, e.g. "pathway-xxxxxxx.svc.aped-1234-a56b.pinecone.io".
#
# Set this and the client talks ONLY to the data plane. Leave it empty and
# pc.Index(name) must first call describe_index on api.pinecone.io to discover
# the host — a control-plane round trip that is NOT covered by the read bound
# below (that wraps query/fetch/describe_index_stats on the data plane) and has
# no timeout of its own.
#
# That gap is not theoretical. Measured 2026-07-26 (bench/server_eyes.log):
#
#   22:38:41  Connecting vector store...
#   22:47:41  search failed: HTTPSConnectionPool(host='api.pinecone.io') Max
#             retries exceeded
#   22:47:41  [stream] hung - emitting hiccup
#
# 540 seconds inside store construction, on the event loop, while the DATA plane
# was answering in 1-2 s. Pinning the host makes a control-plane outage a
# non-event for serving traffic, and it is the vendor's own recommendation:
# "In production situations ... you can eliminate a round trip to the Pinecone
# control plane by specifying the host of the index" (Pinecone.Index docstring).
#
# Find it once with:
#   curl -H "Api-Key: $PINECONE_API_KEY" https://api.pinecone.io/indexes/$PINECONE_INDEX_NAME
# It is stable for the life of the index. Unset = today's behaviour (lookup).
PINECONE_INDEX_HOST: str = os.environ.get("PINECONE_INDEX_HOST", "").strip()


def _is_timeout(exc: BaseException) -> bool:
    """True for the urllib3 errors a ``_request_timeout`` produces."""
    from urllib3.exceptions import MaxRetryError
    from urllib3.exceptions import TimeoutError as Urllib3Timeout

    if isinstance(exc, (Urllib3Timeout, MaxRetryError)):
        return True
    return isinstance(getattr(exc, "reason", None), Urllib3Timeout)


class _BoundedPineconeIndex:
    """Wraps ``pinecone.data.Index`` and puts a wall-clock bound on READS.

    Only ``query`` / ``fetch`` / ``describe_index_stats`` are bounded — the calls
    the retrieval path makes. Writes (``upsert``, ``delete``) are legitimately
    slower and are forwarded untouched via ``__getattr__``, so the ingestion CLI
    keeps the vendor's behaviour exactly. A caller-supplied ``_request_timeout``
    always wins (``setdefault``).

    ``query`` additionally drops the embedding projection (see
    ``PINECONE_INCLUDE_VALUES_ENABLED``). That one is ASSIGNED, not
    ``setdefault``-ed, and the difference matters: the vendor store passes
    ``include_values`` EXPLICITLY on every call (hard-coded ``True`` in 0.1.3,
    ``kwargs.pop("include_values", True)`` in 0.1.9), so a default could never
    win — there is no call where the key is absent. Forcing it here is also why
    this lives in the wrapper rather than in ``vector_store_kwargs`` at the six
    ``as_retriever`` call sites plus the CLI scripts: "this application never
    reads Pinecone-returned vectors" is a fact about the transport, and against a
    hard egress cap one missed call site re-opens the leak.
    """

    __slots__ = ("_index", "_read_timeout")

    def __init__(self, index: Any, read_timeout: Optional[float]) -> None:
        self._index = index
        self._read_timeout = read_timeout if read_timeout and read_timeout > 0 else None

    def _bound(self, kwargs: dict) -> dict:
        if self._read_timeout is not None:
            kwargs.setdefault("_request_timeout", self._read_timeout)
        return kwargs

    def _call(self, name: str, args: tuple, kwargs: dict) -> Any:
        started = time.monotonic()
        try:
            return getattr(self._index, name)(*args, **self._bound(kwargs))
        except Exception as exc:
            # Make a fired bound ATTRIBUTABLE. Callers upstream swallow retrieval
            # errors into an empty tray (rag_subagent, supervisor_orchestrator),
            # so without this an over-tight bound would silently shrink retrieval
            # instead of showing up in the logs. Behaviour is unchanged — the
            # error is re-raised.
            if _is_timeout(exc):
                logger.error(
                    "[pinecone] %s exceeded the %ss bound after %.1fs (%s) — this "
                    "call returns no nodes; raise PINECONE_REQUEST_TIMEOUT_SECONDS "
                    "if the link is healthy but slow",
                    name, self._read_timeout, time.monotonic() - started,
                    type(exc).__name__,
                )
            raise

    def query(self, *args: Any, **kwargs: Any) -> Any:
        if not PINECONE_INCLUDE_VALUES_ENABLED:
            # Assigned, not setdefault — the vendor always supplies this key.
            kwargs["include_values"] = False
        return self._call("query", args, kwargs)

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("fetch", args, kwargs)

    def describe_index_stats(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("describe_index_stats", args, kwargs)

    def __getattr__(self, name: str) -> Any:
        # Everything else (upsert, delete, list, .config, plugins, ...) behaves
        # exactly as the vendor Index does.
        return getattr(self._index, name)


def _build_retry() -> Any:
    """Bounded urllib3 retry policy for the shared pool.

    Pinned in code, not env: urllib3's default is ``Retry(3)`` — 4 connect
    attempts, each with its OWN fresh timeout budget — so a "20 s" bound would
    silently mean 80 s. ``Configuration.retries`` is the one retry knob this
    client forwards to the pool.

    ``read=False`` is not a behaviour change: POST is not in urllib3's retryable
    methods, so ``/query`` read errors were never retried anyway.

    ``total=1`` (2 attempts), not 2, because this policy demonstrably bounds only
    ONE layer: with ``total=2`` a 20 s per-attempt bound still produced a
    MaxRetryError after 182 s, i.e. ~9 attempts, so the pool manager and the
    connection pool are each applying retries of their own. Halving the attempts
    this layer contributes is the part we control; the per-attempt bound above is
    sized so that even the observed multiplier stays inside the stream watchdog.
    One connect retry still absorbs a single dropped handshake on a flaky link,
    which is the common case here.
    """
    from urllib3 import Retry

    return Retry(
        total=1, connect=1, read=False, redirect=0, status=0,
        backoff_factor=0.5, raise_on_status=False,
    )


_store_lock = threading.Lock()
_store_cache: Optional[Tuple[Tuple[Any, ...], PineconeVectorStore]] = None


def reset_vector_store_cache() -> None:
    """Drop the cached store. For tests and for scripts that re-point env."""
    global _store_cache
    with _store_lock:
        _store_cache = None


def _build_store(
    api_key: str, index_name: str, environment: str
) -> PineconeVectorStore:
    from pinecone import Pinecone

    # source_tag matches what the vendor store passes when it builds the client
    # itself, so Pinecone-side user-agent/telemetry is unchanged.
    pc = Pinecone(api_key=api_key, source_tag="llamaindex")
    pc.openapi_config.connection_pool_maxsize = PINECONE_POOL_MAXSIZE
    pc.openapi_config.retries = _build_retry()

    # host= skips the control-plane describe_index round trip entirely; name= is
    # the fallback and keeps today's behaviour when the host is not configured.
    raw_index = (
        pc.Index(host=PINECONE_INDEX_HOST)
        if PINECONE_INDEX_HOST
        else pc.Index(index_name)
    )
    bounded = _BoundedPineconeIndex(raw_index, PINECONE_REQUEST_TIMEOUT_SECONDS)
    return PineconeVectorStore(
        pinecone_index=bounded,
        api_key=api_key,
        index_name=index_name,
        environment=environment,
    )


def get_vector_store() -> PineconeVectorStore:
    global _store_cache

    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    environment = os.getenv("PINECONE_ENVIRONMENT")
    if not api_key or not index_name or not environment:
        raise ValueError(
            "Please set PINECONE_API_KEY, PINECONE_INDEX_NAME, and PINECONE_ENVIRONMENT"
            " to your environment variables or config them in the .env file"
        )

    if not PINECONE_STORE_CACHE_ENABLED:
        return _build_store(api_key, index_name, environment)

    # Credentials stay a CALL-time read (unchanged from before), so the cache is
    # keyed on them: re-point any of the three and the next call rebuilds. Pool
    # size is in the key too because it is baked into the PoolManager.
    cache_key = (api_key, index_name, environment, PINECONE_POOL_MAXSIZE)

    cached = _store_cache
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    with _store_lock:
        cached = _store_cache
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        store = _build_store(api_key, index_name, environment)
        logger.info(
            "[pinecone] vector store created for index=%s (reused for this process; "
            "read bound %ss per attempt, pool %s, values %s, host %s)",
            index_name, PINECONE_REQUEST_TIMEOUT_SECONDS or "off", PINECONE_POOL_MAXSIZE,
            "on (~16x read egress)" if PINECONE_INCLUDE_VALUES_ENABLED else "off",
            PINECONE_INDEX_HOST or "via control-plane lookup",
        )
        _store_cache = (cache_key, store)
        return store
