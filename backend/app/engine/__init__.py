from datetime import datetime
from zoneinfo import ZoneInfo

from app.engine.audience_guard import AudienceGuardPostprocessor
from app.engine.index import get_index
from app.engine.node_postprocessors import NodeCitationProcessor
from app.engine.prompts import CONDENSE_PROMPT_TEMPLATE, CONTEXT_PROMPT, build_system_prompt
from fastapi import HTTPException
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from llama_index.core.memory import ChatMemoryBuffer

from app.engine.custom_condense_plus_context import CustomCondensePlusContextChatEngine


def get_chat_engine(filters=None, params=None, timezone: str = "UTC") -> CustomCondensePlusContextChatEngine:
    # The audience guard runs first, so a wrong-audience node never reaches
    # rerank, the context, or the sources annotation.
    audience_guard = AudienceGuardPostprocessor()
    node_postprocessors = [audience_guard, NodeCitationProcessor()]

    index = get_index(params)
    if index is None:
        raise HTTPException(
            status_code=500,
            detail="Vector index is unavailable",
        )

    retriever_k = 35
    sparse_k = retriever_k * 5
    query_mode = VectorStoreQueryMode.DEFAULT

    retriever = index.as_retriever(
        vector_store_query_mode=query_mode,
        similarity_top_k=retriever_k,
        sparse_top_k=sparse_k,
        filters=filters,
    )

    # Use user's timezone to determine current date and time
    try:
        now = datetime.now(ZoneInfo(timezone))
    except Exception:
        # Fallback to UTC if the provided timezone is invalid
        now = datetime.now(ZoneInfo("UTC"))

    # Format: "March 23, 2026 at 9:17 AM MDT"
    current_date = now.strftime("%B %d, %Y")
    current_time = now.strftime("%I:%M %p").lstrip('0')  # Remove leading zero from hour
    tz_abbr = now.strftime("%Z")  # Timezone abbreviation (e.g., MDT, PST, UTC)
    current_datetime = f"{current_date} at {current_time} {tz_abbr}"

    # token_limit is the TOTAL budget for system prompt + retrieved context +
    # chat history; ChatMemoryBuffer.get() raises if system + context alone
    # exceed it. Measured with tiktoken (o200k_base), 2026-10-19:
    #   - system prompt (final, Phase 3):          ~820 tokens
    #   - CONTEXT_PROMPT without contexts:          ~160 tokens
    #   - retrieved contexts (top 17, merged):    1,600-2,300 tokens
    # ~3,200 at most, leaving ~20K for chat history (upstream's ~8K missionary
    # prompt left 9-12K). Re-measure before adding a prompt block.
    memory = ChatMemoryBuffer.from_defaults(token_limit=24000)

    engine = CustomCondensePlusContextChatEngine.from_defaults(
        system_prompt=build_system_prompt(current_datetime),
        context_prompt=CONTEXT_PROMPT,
        condense_prompt=CONDENSE_PROMPT_TEMPLATE,
        skip_condense=False,  # Enable question condensation with conversation history
        retriever=retriever,
        node_postprocessors=node_postprocessors,
        verbose=True,
        memory=memory  # Add memory buffer for conversation context
    )
    # Public handle on this request's guard: the orchestrator reads its drop
    # count, and refuses to run an engine that lacks one.
    engine.audience_guard = audience_guard
    return engine
