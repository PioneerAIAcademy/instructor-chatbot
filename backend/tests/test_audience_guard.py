"""Filter shape for the server-pinned instructor audience (CLAUDE.md §7 Phase 1).

Phase 1 extends this file with the index guard and the post-retrieval role
assertion.
"""

from llama_index.core.vector_stores.types import FilterOperator

from app.engine.audience_guard import instructor_filters
from app.engine.custom_condense_plus_context import source_label


def _by_key(filters):
    return {f.key: f for f in filters.filters}


def test_filter_is_role_instructor_and_source_in_defaults(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_SOURCES", raising=False)
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


def test_source_label_instructor_guide():
    meta = {"title": "Pay Dates", "source": "instructor-assistant", "url": "https://x.example/pay"}
    assert source_label(meta) == "[Source: Pay Dates — instructor guide]"


def test_source_label_external_page_names_host():
    meta = {
        "title": "AI and Academic Honesty",
        "source": "instructor-assistant-linked",
        "url": "https://www.byui.edu/genai/",
    }
    assert source_label(meta) == "[Source: AI and Academic Honesty — external page (www.byui.edu)]"
