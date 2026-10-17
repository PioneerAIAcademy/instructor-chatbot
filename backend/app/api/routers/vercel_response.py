import asyncio
import inspect
import os
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from aiostream import stream
from fastapi import Request
from fastapi.responses import StreamingResponse
from llama_index.core.chat_engine.types import StreamingAgentChatResponse

from app.api.routers.events import EventCallbackHandler
from app.api.routers.message_variations import get_retrieval_start_message
from app.api.routers.models import ChatData, Message, SourceNodes
from app.api.services.suggestion import NextQuestionSuggestion
from app.utils.localization import LocalizationManager
from app.utils.date_spans import extract_date_spans

logger = logging.getLogger("uvicorn")

# Delay (in seconds) between each streamed *character*, for a visible
# letter-by-letter typewriter feel. 0.004 ≈ ~250 chars/sec — a 2,000-char
# answer reveals in ~8s. Set TYPEWRITER_CHUNK_DELAY=0 for an instant flush.
TYPEWRITER_CHUNK_DELAY: float = float(os.getenv("TYPEWRITER_CHUNK_DELAY", "0.004"))

# Stream-level safety net: if upstream OpenAI / supervisor hangs, the SSE
# generator can sit silently forever and the user sees a stuck "THINKING…"
# indicator (upstream incident 2026-05-19 — transient OpenAI DNS failures).
# Clamp the initial response wait + per-token gap so a stuck request closes
# cleanly with a user-visible hiccup message instead of an infinite spinner.
STREAM_RESPONSE_INITIAL_TIMEOUT_SECONDS = 180.0
STREAM_TOKEN_GAP_TIMEOUT_SECONDS = 45.0

_STREAM_HICCUP_MESSAGES: dict[str, str] = {
    "en": "Sorry — I hit a service hiccup. Please try asking again.",
    "es": "Lo siento — hubo un problema con el servicio. Por favor, inténtalo de nuevo.",
    "pt": "Desculpe — houve um problema com o serviço. Por favor, tente novamente.",
    "fr": "Désolé — un problème de service est survenu. Veuillez réessayer.",
    "it": "Spiacenti — si è verificato un problema con il servizio. Per favore riprova.",
}


# Padding appended to every typewriter chunk so that the TCP payload is large
# enough to bypass Nagle's algorithm and proxy write-coalescing.  The Vercel AI
# SDK parser splits on "\n" and filters out empty lines, so extra newlines are
# harmless.  64 bytes of padding pushes even a single-character text token
# (e.g., ``0:"H"\n``) above the typical ~80-byte threshold that triggers an
# immediate TCP send.
_STREAM_FLUSH_PADDING = "\n" * 64


class VercelStreamResponse(StreamingResponse):
    """
    Class to convert the response from the chat engine to the streaming format expected by Vercel
    """

    TEXT_PREFIX = "0:"
    DATA_PREFIX = "8:"
    ERROR_PREFIX = "3:"

    @classmethod
    def convert_text(cls, token: str):
        # Escape newlines and double quotes to avoid breaking the stream
        token = json.dumps(token)
        return f"{cls.TEXT_PREFIX}{token}\n{_STREAM_FLUSH_PADDING}"

    @classmethod
    def convert_data(cls, data: dict):
        data_str = json.dumps(data)
        return f"{cls.DATA_PREFIX}[{data_str}]\n{_STREAM_FLUSH_PADDING}"

    @classmethod
    def convert_error(cls, message: str):
        message_str = json.dumps(message)
        return f"{cls.ERROR_PREFIX}{message_str}\n{_STREAM_FLUSH_PADDING}"

    @classmethod
    def _iter_text_chunks(cls, text: str):
        """Yield individual characters for letter-by-letter typewriter rendering.

        Newline sequences are yielded as a single chunk so paragraph breaks
        appear instantly rather than introducing extra delays.
        """
        if not text:
            return
        i = 0
        while i < len(text):
            if text[i] == "\n":
                # Gather consecutive newlines into one chunk
                j = i
                while j < len(text) and text[j] == "\n":
                    j += 1
                yield text[i:j]
                i = j
            else:
                yield text[i]
                i += 1

    def __init__(
        self,
        request: Request,
        event_handler: EventCallbackHandler,
        response: StreamingAgentChatResponse | Awaitable[StreamingAgentChatResponse],
        chat_data: ChatData,
        trace_id: str | None = None,
        skip_suggestions: bool = False,
        user_language: str | None = None,
        on_stream_end: Optional[Callable[[str], Awaitable[None]]] = None,
        emit_initial_status: bool = True,
    ):
        content = VercelStreamResponse.content_generator(
            request,
            event_handler,
            response,
            chat_data,
            trace_id,
            skip_suggestions,
            user_language,
            on_stream_end,
            emit_initial_status,
        )
        # Use text/event-stream so reverse proxies (Render, Nginx, Cloudflare)
        # recognise this as a streaming connection and disable response buffering.
        super().__init__(content=content, media_type="text/event-stream")
        # Prevent proxy / browser buffering so each character-level chunk
        # reaches the client immediately for a visible typewriter effect.
        self.headers["Cache-Control"] = "no-cache, no-transform"
        self.headers["X-Accel-Buffering"] = "no"
        self.headers["Connection"] = "keep-alive"

    @classmethod
    async def content_generator(
        cls,
        request: Request,
        event_handler: EventCallbackHandler,
        response: StreamingAgentChatResponse | Awaitable[StreamingAgentChatResponse],
        chat_data: ChatData,
        trace_id: str | None = None,
        skip_suggestions: bool = False,
        user_language: str | None = None,
        on_stream_end: Optional[Callable[[str], Awaitable[None]]] = None,
        emit_initial_status: bool = True,
    ):
        final_response = ""
        resolved_response: StreamingAgentChatResponse | None = None
        response_task: asyncio.Task[StreamingAgentChatResponse] | None = None

        # The pipeline status indicator follows the language the user
        # PROMPTED in — detected straight from the message text, NOT the
        # app UI-language pref (`user_language`, which a manual picker can
        # override). This keeps the indicator consistent with the reply,
        # which mirrors the prompt language. Falls back to "en" on any
        # detection failure.
        try:
            _indicator_lang = LocalizationManager.detect_language(
                chat_data.get_last_message_content()
            )
        except Exception:
            _indicator_lang = "en"
        if inspect.isawaitable(response):
            response_task = asyncio.create_task(response)
        else:
            resolved_response = response

        async def _chat_response_generator():
            nonlocal final_response, resolved_response

            final_response = ""
            token_count = 0

            try:
                if resolved_response is None:
                    assert response_task is not None
                    resolved_response = await asyncio.wait_for(
                        response_task,
                        timeout=STREAM_RESPONSE_INITIAL_TIMEOUT_SECONDS,
                    )

                # Use manual __anext__() with per-token timeout so a hung
                # upstream LLM can't lock the SSE generator forever.
                token_gen = resolved_response.async_response_gen()
                while True:
                    try:
                        token = await asyncio.wait_for(
                            token_gen.__anext__(),
                            timeout=STREAM_TOKEN_GAP_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        break
                    final_response += token
                    token_count += 1
                    for chunk in cls._iter_text_chunks(token):
                        yield cls.convert_text(chunk)
                        await asyncio.sleep(TYPEWRITER_CHUNK_DELAY)

            except Exception as exc:
                # A hang (TimeoutError) or a failed answer (e.g. the
                # orchestrator's SynthesisFailedError) both end in the same
                # localized hiccup text — never a blank answer with sources,
                # and never internal exception text sent to the client.
                event_handler.is_done = True
                lang = (user_language or "en").lower().split("-")[0]
                msg = _STREAM_HICCUP_MESSAGES.get(lang, _STREAM_HICCUP_MESSAGES["en"])
                logger.error(
                    "[stream] %s — emitting hiccup. lang=%s tokens_before=%d",
                    "hung" if isinstance(exc, asyncio.TimeoutError) else f"failed: {exc!r}",
                    lang, token_count,
                )
                final_response = msg
                for chunk in cls._iter_text_chunks(msg):
                    yield cls.convert_text(chunk)
                    await asyncio.sleep(TYPEWRITER_CHUNK_DELAY)
                return

            # Fire suggestion generation NOW so the LLM call runs while
            # we emit date spans, sources, and other post-stream data.
            suggestion_task: asyncio.Task | None = None
            if not skip_suggestions:
                conversation = chat_data.messages + [
                    Message(role="assistant", content=final_response, trace_id=trace_id)
                ]
                # Suggestion generation runs inside the SSE generator, after
                # chat()'s @observe context has been popped — so without a
                # parent hint @observe(name="suggestion-generation") would open
                # its own root trace. Thread the chat trace_id so it nests under
                # the single `chat` trace. langfuse_parent_trace_id is honored
                # by the v2 decorator only when the contextvar stack is empty
                # (our case here); None (Langfuse unconfigured) is a safe no-op.
                suggestion_task = asyncio.create_task(
                    NextQuestionSuggestion.suggest_next_questions(
                        conversation,
                        source_nodes=resolved_response.source_nodes if resolved_response else None,
                        user_language=user_language,
                        langfuse_parent_trace_id=trace_id,
                    )
                )

            # Dates in the answer text, highlighted by the frontend markdown renderer.
            date_spans = extract_date_spans(final_response, user_language)
            if date_spans:
                yield cls.convert_data(
                    {
                        "type": "date_spans",
                        "data": {
                            "phrases": date_spans,
                            "language": user_language,
                        },
                        "trace_id": trace_id,
                    }
                )

            # the text_generator is the leading stream, once it's finished, also finish the event stream
            event_handler.is_done = True

            # Yield user language for frontend localization
            if user_language:
                yield cls.convert_data(
                    {
                        "type": "user_language",
                        "data": {"language": user_language},
                        "trace_id": trace_id,
                    }
                )

            # Yield the source nodes
            yield cls.convert_data(
                {
                    "type": "sources",
                    "data": {
                        "nodes": [
                            SourceNodes.from_source_node(node).model_dump()
                            for node in (resolved_response.source_nodes if resolved_response else [])
                        ]
                    },
                    "trace_id": trace_id,
                }
            )

            # Await the suggestion task that was fired earlier (ran in
            # parallel with date spans, user_language, and sources).
            if suggestion_task is not None:
                try:
                    questions = await suggestion_task
                except Exception:
                    questions = []
                if questions:
                    yield cls.convert_data(
                        {
                            "type": "suggested_questions",
                            "data": questions,
                            "trace_id": trace_id,
                        }
                    )

        # Yield the events from the event handler
        async def _event_generator():
            async for event in event_handler.async_event_gen():
                event_response = event.to_response()
                if event_response is not None:
                    event_response["trace_id"] = trace_id
                    yield cls.convert_data(event_response)

        try:
            # Stream a blank message early so the client creates the assistant message
            yield cls.convert_text("")

            # Emit a status the INSTANT the SSE stream opens so the
            # thinking indicator never flashes blank.
            if emit_initial_status:
                yield cls.convert_data(
                    {
                        "type": "events",
                        "data": {"title": get_retrieval_start_message(_indicator_lang)},
                        "trace_id": trace_id,
                    }
                )

            combine = stream.merge(
                _chat_response_generator(), _event_generator()
            )
            async with combine.stream() as streamer:
                async for output in streamer:
                    yield output

                    if await request.is_disconnected():
                        break
        finally:
            # Ensure the event stream can terminate even if the client disconnects early.
            event_handler.is_done = True
            if response_task is not None and not response_task.done():
                response_task.cancel()
            if on_stream_end is not None:
                await on_stream_end(final_response)
