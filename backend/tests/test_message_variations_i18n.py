"""Tests for localized pipeline status messages (message_variations.py).

The pipeline status indicator must follow the language the user
prompted in. Every message pool must cover the 9 supported languages,
and every getter must honor its `lang` argument.
"""

import pytest

from app.api.routers import message_variations as mv

_SUPPORTED = ("en", "es", "pt", "fr", "it", "ja", "ko", "zh", "tl")

_POOLS = {
    "RETRIEVAL_MESSAGES": mv.RETRIEVAL_MESSAGES,
    "QUERY_MESSAGES": mv.QUERY_MESSAGES,
    "SYNTHESIZE_MESSAGES": mv.SYNTHESIZE_MESSAGES,
    "LLM_MESSAGES": mv.LLM_MESSAGES,
    "RERANKING_MESSAGES": mv.RERANKING_MESSAGES,
}

_GETTERS = (
    mv.get_retrieval_start_message,
    mv.get_query_message,
    mv.get_synthesize_message,
    mv.get_llm_message,
    mv.get_reranking_message,
)


@pytest.mark.parametrize("name,pool", _POOLS.items())
def test_pool_covers_every_supported_language(name, pool):
    for lang in _SUPPORTED:
        assert lang in pool, f"{name} missing language '{lang}'"
        assert pool[lang], f"{name}[{lang}] is empty"
        for variant in pool[lang]:
            assert variant and variant.strip(), f"{name}[{lang}] has a blank variant"


@pytest.mark.parametrize("getter", _GETTERS)
def test_getter_defaults_to_english(getter):
    msg = getter()
    assert isinstance(msg, str) and msg.strip()


@pytest.mark.parametrize("getter", _GETTERS)
@pytest.mark.parametrize("lang", _SUPPORTED)
def test_getter_returns_string_for_every_lang(getter, lang):
    msg = getter(lang)
    assert isinstance(msg, str) and msg.strip()


def test_spanish_getter_returns_spanish():
    # The Spanish retrieval message must not be the English one.
    es = mv.get_retrieval_start_message("es")
    assert es in mv.RETRIEVAL_MESSAGES["es"]
    assert es not in mv.RETRIEVAL_MESSAGES["en"]


def test_unsupported_language_falls_back_to_english():
    msg = mv.get_query_message("de")  # German not supported
    assert msg in mv.QUERY_MESSAGES["en"]


def test_region_code_normalized():
    msg = mv.get_query_message("pt-BR")
    assert msg in mv.QUERY_MESSAGES["pt"]


def test_none_language_falls_back_to_english():
    msg = mv.get_query_message(None)
    assert msg in mv.QUERY_MESSAGES["en"]
