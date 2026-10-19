"""Audience isolation for the Instructor Assistant (CLAUDE.md §7 Phase 1).

Three layers, all server-side. Nothing the client sends (upstream's
`data.role`, uploaded doc IDs, agenda scope) takes part in any of them.

1. `check_index_config()` — boot fails unless PINECONE_INDEX_NAME is on the
   ALLOWED_INDEX_NAMES list, and PINECONE_INDEX_HOST (when set) is that same
   index's host. The missionary index, and copies named after it, are refused
   even if someone lists them.
2. `instructor_filters()` — the Pinecone metadata filter on every query.
3. `AudienceGuardPostprocessor` — after retrieval, drops any node whose role
   or source is wrong and logs `audience_leak`. It should never fire; when
   it does, that is a security finding, not noise.

CLAUDE.md §0 rule 5: never weaken any of these to make a test or eval pass.
"""

import logging
import os
from typing import List, Optional

from llama_index.core import QueryBundle
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters

logger = logging.getLogger("uvicorn")

INSTRUCTOR_ROLE = "instructor"

DEFAULT_RETRIEVAL_SOURCES = ("instructor-assistant", "instructor-assistant-linked")

DEFAULT_ALLOWED_INDEX_NAMES = ("instructor-assistant",)

# The Missionary Assistant's index, plus copies of it named after it
# ("pathway-staging", "pathway_v2"), and any index named for missionaries.
# Refused even when listed in ALLOWED_INDEX_NAMES: the allow-list is for
# staging copies of the instructor index, never for the other audience. This
# catches the known names; the allow-list and the separate Pinecone account
# (CLAUDE.md §13 Q4) remain the real controls.
_DENIED_INDEX_PREFIX = "pathway"
_DENIED_INDEX_SUBSTRING = "missionar"


def is_denied_index_name(name: str) -> bool:
    lowered = name.strip().lower()
    return (
        lowered == _DENIED_INDEX_PREFIX
        or lowered.startswith((f"{_DENIED_INDEX_PREFIX}-", f"{_DENIED_INDEX_PREFIX}_"))
        or _DENIED_INDEX_SUBSTRING in lowered
    )

AUDIENCE_LEAK_TAG = "guard:audience_leak"


class IndexConfigError(RuntimeError):
    """The Pinecone index settings would point the bot at the wrong index."""


def _csv_env(name: str, default: tuple[str, ...]) -> list[str]:
    values = [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]
    return values or list(default)


def retrieval_sources() -> list[str]:
    """`source` values retrieval may return, from RETRIEVAL_SOURCES (comma-separated)."""
    return _csv_env("RETRIEVAL_SOURCES", DEFAULT_RETRIEVAL_SOURCES)


def allowed_index_names() -> list[str]:
    """Index names the bot may use, from ALLOWED_INDEX_NAMES (comma-separated)."""
    return _csv_env("ALLOWED_INDEX_NAMES", DEFAULT_ALLOWED_INDEX_NAMES)


def _host_index_name(host: str) -> str:
    """The index name a Pinecone data-plane host belongs to.

    Hosts look like `<index-name>-<project-id>.svc.<region>.pinecone.io`; the
    project id has no hyphen, so the index name is the first DNS label minus
    its last `-segment`. Returns "" for anything that isn't a Pinecone host.
    """
    bare = host.strip().lower()
    for scheme in ("https://", "http://"):
        if bare.startswith(scheme):
            bare = bare[len(scheme):]
    bare = bare.split("/", 1)[0].split(":", 1)[0]
    if not bare.endswith(".pinecone.io"):
        return ""
    label = bare.split(".", 1)[0]
    if "-" not in label:
        return ""
    return label.rsplit("-", 1)[0]


def check_index_config(
    index_name: Optional[str] = None, index_host: Optional[str] = None
) -> str:
    """Raise IndexConfigError unless the configured index is an allowed one.

    Reads PINECONE_INDEX_NAME / PINECONE_INDEX_HOST when not passed. Returns
    the index name. Messages name the variable, never a key.
    """
    name = (index_name if index_name is not None else os.getenv("PINECONE_INDEX_NAME", "")).strip()
    host = (index_host if index_host is not None else os.getenv("PINECONE_INDEX_HOST", "")).strip()

    if not name:
        raise IndexConfigError("PINECONE_INDEX_NAME is not set")
    if is_denied_index_name(name):
        raise IndexConfigError(
            f"PINECONE_INDEX_NAME={name!r} is the Missionary Assistant's index; refusing to start"
        )
    allowed = allowed_index_names()
    denied_listed = [n for n in allowed if is_denied_index_name(n)]
    if denied_listed:
        raise IndexConfigError(
            f"ALLOWED_INDEX_NAMES lists {sorted(denied_listed)}, which is never allowed"
        )
    if name not in allowed:
        raise IndexConfigError(
            f"PINECONE_INDEX_NAME={name!r} is not in ALLOWED_INDEX_NAMES {allowed}"
        )
    if host:
        host_index = _host_index_name(host)
        if host_index != name:
            raise IndexConfigError(
                "PINECONE_INDEX_HOST does not belong to PINECONE_INDEX_NAME "
                f"(host is for {host_index or 'a non-Pinecone host'!r}, expected {name!r})"
            )
    return name


def instructor_filters() -> MetadataFilters:
    """`role == "instructor"` AND `source in RETRIEVAL_SOURCES`. Takes no client input."""
    return MetadataFilters(
        filters=[
            MetadataFilter(key="role", value=INSTRUCTOR_ROLE),
            MetadataFilter(key="source", value=retrieval_sources(), operator="in"),
        ],
        condition="and",
    )


def assert_instructor_nodes(nodes: List[NodeWithScore]) -> tuple[List[NodeWithScore], int]:
    """Keep only nodes with role == instructor and an allowed source.

    Returns (kept, dropped_count). Every drop is logged at ERROR as
    `audience_leak` with the node's id, slug, role, and source.
    """
    sources = set(retrieval_sources())
    kept: List[NodeWithScore] = []
    dropped = 0
    for node_with_score in nodes:
        metadata = getattr(node_with_score.node, "metadata", None) or {}
        role = metadata.get("role")
        source = metadata.get("source")
        if role == INSTRUCTOR_ROLE and source in sources:
            kept.append(node_with_score)
            continue
        dropped += 1
        logger.error(
            "audience_leak: dropped node id=%s slug=%s role=%r source=%r",
            node_with_score.node.node_id, metadata.get("slug"), role, source,
        )
    return kept, dropped


class AudienceGuardPostprocessor(BaseNodePostprocessor):
    """Runs `assert_instructor_nodes` first among the engine's postprocessors,
    so a wrong-audience node never reaches rerank, context, or sources.

    One instance per chat engine (per request); `dropped` counts its drops.
    """

    dropped: int = 0

    @classmethod
    def class_name(cls) -> str:
        return "AudienceGuardPostprocessor"

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        kept, dropped = assert_instructor_nodes(nodes)
        self.dropped += dropped
        return kept
