"""Audience isolation for the Instructor Assistant.

Retrieval is pinned to instructor content on the server. Nothing the client
sends (upstream's `data.role`, uploaded doc IDs, agenda scope) takes part in
the filter. CLAUDE.md §0 rule 5: never weaken this to make a test pass.

Phase 1 adds the startup index guard and the post-retrieval role assertion
alongside `instructor_filters()`.
"""

import os

from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters

INSTRUCTOR_ROLE = "instructor"

DEFAULT_RETRIEVAL_SOURCES = ("instructor-assistant", "instructor-assistant-linked")


def retrieval_sources() -> list[str]:
    """`source` values retrieval may return, from RETRIEVAL_SOURCES (comma-separated)."""
    raw = os.getenv("RETRIEVAL_SOURCES", "")
    sources = [s.strip() for s in raw.split(",") if s.strip()]
    return sources or list(DEFAULT_RETRIEVAL_SOURCES)


def instructor_filters() -> MetadataFilters:
    """`role == "instructor"` AND `source in RETRIEVAL_SOURCES`. Takes no client input."""
    return MetadataFilters(
        filters=[
            MetadataFilter(key="role", value=INSTRUCTOR_ROLE),
            MetadataFilter(key="source", value=retrieval_sources(), operator="in"),
        ],
        condition="and",
    )
