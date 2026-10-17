import logging
import os
from llama_index.core.callbacks import CallbackManager
from llama_index.core.settings import Settings

logger = logging.getLogger(__name__)


def init_settings():
    # MUST run BEFORE any provider init that creates Settings.llm /
    # Settings.embed_model. Those constructors capture Settings.callback_manager
    # at construction time — if it's None then, the LLM caches None and every
    # later call raises 'NoneType' object has no attribute 'start_trace' /
    # 'event_starts_to_ignore' from inside llama-index's tracing decorator.
    if Settings.callback_manager is None:
        handlers = []
        try:
            from app.utils.langfuse_llama_index import LangfuseLlamaIndexHandler
            handlers.append(LangfuseLlamaIndexHandler())
            logger.info("Langfuse llama-index callback handler attached")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Langfuse llama-index handler init failed (%s); RAG LLM "
                "calls will not appear in Langfuse traces",
                exc,
            )
        Settings.callback_manager = CallbackManager(handlers=handlers)

    # Only OpenAI is wired: the index was embedded with text-embedding-3-large,
    # so the query embedder must match it. Other upstream providers were dropped.
    model_provider = os.getenv("MODEL_PROVIDER")
    if model_provider != "openai":
        raise ValueError(f"Invalid model provider: {model_provider}")
    init_openai()

    Settings.chunk_size = int(os.getenv("CHUNK_SIZE", "1024"))
    Settings.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "20"))


def init_openai():
    # from llama_index.core.constants import DEFAULT_TEMPERATURE
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai import OpenAI

    max_tokens = os.getenv("LLM_MAX_TOKENS")
    config = {
        "model": os.getenv("MODEL"),
        # "temperature": float(os.getenv("LLM_TEMPERATURE", 0)),
        "temperature": float(0),
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
    }
    Settings.llm = OpenAI(**config)

    dimensions = os.getenv("EMBEDDING_DIM")
    config = {
        "model": os.getenv("EMBEDDING_MODEL"),
        "dimensions": int(dimensions) if dimensions is not None else None,
        # Bound the embedding client. llama-index's own defaults are timeout=60.0
        # and max_retries=10, i.e. up to ~11 x 60 s of request plus ~55 s of
        # exponential backoff (openai SDK INITIAL_RETRY_DELAY 0.5, MAX 8.0) =
        # ~715 s on ONE query embed. Only the two sub-agent asyncio.wait_for
        # calls bound it at all upstream; the chat engine's embeds have no
        # per-call cap below the 180 s stream watchdog.
        # 20 s / 3 retries: a healthy embed is 0.3-0.6 s on prod and a couple of
        # seconds on the slow dev box, so 20 s is >30x headroom, and 4 total
        # attempts still ride out a 429/5xx blip (the openai SDK's own default is
        # max_retries=2). Worst case drops ~715 s -> ~84 s. Failure degrades the
        # same way a Pinecone failure does — an empty tray, which the synthesis
        # prompt turns into an honest refusal, never a fabrication.
        "timeout": float(os.getenv("OPENAI_EMBED_TIMEOUT_SECONDS", "20") or "20"),
        "max_retries": int(os.getenv("OPENAI_EMBED_MAX_RETRIES", "3") or "3"),
    }
    Settings.embed_model = OpenAIEmbedding(**config)
