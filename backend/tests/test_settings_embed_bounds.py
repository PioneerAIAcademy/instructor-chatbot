import os
from unittest.mock import patch
import pytest
from llama_index.core.settings import Settings
from app.settings import init_openai

_ENV = {"MODEL_PROVIDER": "openai", "MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-test", "EMBEDDING_MODEL": "text-embedding-3-large",
        "EMBEDDING_DIM": "3072"}

@pytest.fixture(autouse=True)
def _restore_settings():
    llm, embed = Settings._llm, Settings._embed_model
    yield
    Settings._llm, Settings._embed_model = llm, embed

def test_embedding_client_is_bounded_by_default():
    with patch.dict(os.environ, _ENV, clear=True):
        init_openai()
    em = Settings.embed_model
    assert em.timeout == pytest.approx(20.0)
    assert em.max_retries == 3
    assert em._get_aclient().timeout == pytest.approx(20.0)
    assert em._get_aclient().max_retries == 3

def test_embedding_bounds_are_env_tunable():
    with patch.dict(os.environ, {**_ENV, "OPENAI_EMBED_TIMEOUT_SECONDS": "8",
                                "OPENAI_EMBED_MAX_RETRIES": "1"}, clear=True):
        init_openai()
    assert Settings.embed_model.timeout == pytest.approx(8.0)
    assert Settings.embed_model.max_retries == 1

def test_embedding_model_and_dimensions_are_unchanged():
    with patch.dict(os.environ, _ENV, clear=True):
        init_openai()
    em = Settings.embed_model
    assert em.model_name == "text-embedding-3-large"
    assert em.dimensions == 3072
    assert em.embed_batch_size == 100
    assert em.reuse_client is True


def test_init_settings_attaches_the_langfuse_bridge_to_the_llm(monkeypatch):
    """Regression: `Settings.callback_manager is None` is never true (the
    property builds a default), so the bridge was never attached and no
    rag-llm generation was ever recorded."""
    from llama_index.core.settings import Settings

    from app.settings import init_settings
    from app.utils.langfuse_llama_index import LangfuseLlamaIndexHandler

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDING_DIM", "3072")
    init_settings()
    init_settings()  # idempotent: still exactly one bridge

    bridges = [h for h in Settings.callback_manager.handlers if isinstance(h, LangfuseLlamaIndexHandler)]
    assert len(bridges) == 1
    assert any(isinstance(h, LangfuseLlamaIndexHandler) for h in Settings.llm.callback_manager.handlers)
