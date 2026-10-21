import logging
import hashlib
import time
from typing import Any, Optional, Tuple
import traceback
import sys
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from llama_index.core.llms import MessageRole
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.auth import verify_api_key

from app.api.routers.events import EventCallbackHandler
from app.api.routers.models import (
    ChatData,
    DraftEditRequest,
    DraftEditResponse,
    Message,
    ThumbsRequest,
)
from app.api.services.draft_edit import rewrite_selected_text_with_llm
from app.api.tracing import (
    RequestTrace,
    answer_metadata,
    base_metadata,
    chat_tags,
    identity_tags,
    security_tag,
)
from app.redaction import redact
from app.engine.audience_guard import AUDIENCE_LEAK_TAG, INSTRUCTOR_ROLE, instructor_filters
from app.engine.draft_context import (
    build_dropped_draft_notice,
    build_edited_draft_context,
    extract_draft_text,
)
from app.api.routers.vercel_response import VercelStreamResponse
from app.engine.retrieval_orchestrator import RetrievalOrchestrator
from app.security import InputValidator
from app.utils.localization import LocalizationManager
from app.http_client import get_http_client
from app.langfuse import langfuse
import os

chat_router = r = APIRouter()

logger = logging.getLogger("uvicorn")


def _resolve_language(data: "ChatData", text: str) -> tuple[str, bool]:
    """Resolve the user's language for this request, and whether the
    settings pick decided it.

    Precedence (upstream directive 2026-06-01 — the PROMPT's language wins;
    the gear-menu pick is only a BACKUP for when the prompt can't be detected):
      1. CONFIDENT detection of the CURRENT prompt's language → use it.
      2. Else → the SettingsMenu language picker `data.data.user_language_pref`
         (a specific supported code) is the backup.
      3. Else → the detected code (English fallback).

    Upstream also used a geo-IP tiebreaker between 2 and 3; it is not ported.
    The 'auto' pref value means "no manual pick". Unknown / unsupported pref
    codes are dropped silently.

    The second value is True only in case 2: then the model is told to
    answer in that language (its default rule is "the question's language",
    which can't be read from a prompt like "ok").
    """
    pref: str | None = None
    if data.data and isinstance(data.data, dict):
        raw = data.data.get("user_language_pref")
        if (
            isinstance(raw, str) and raw and raw != "auto"
            and LocalizationManager.is_language_supported(raw)
        ):
            pref = LocalizationManager.normalize_language_code(raw)

    detected, confident = LocalizationManager.detect_language_confident(text)

    if confident:
        return detected, False

    if pref:
        logger.info("language: prompt undetectable, using gear pref %s", pref)
        return pref, True

    return detected, False


def _resolve_user_language(data: "ChatData", text: str) -> str:
    """The resolved language code alone (see _resolve_language)."""
    return _resolve_language(data, text)[0]


def _warn_on_client_role(params: dict) -> None:
    """The audience is pinned on the server. A client-sent role is ignored;
    one that isn't `instructor` is worth a log line (old client or probing)."""
    client_role = params.get("role")
    if client_role is not None and client_role != INSTRUCTOR_ROLE:
        logger.warning("Ignoring client-sent role %r; audience is pinned to instructor", client_role)


class _StaticResponse:
    def __init__(self, message: str, source_nodes: Optional[list[Any]] = None):
        self.response = message
        self.source_nodes = source_nodes or []

    async def async_response_gen(self):
        yield self.response


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


def _log_exception_trace():
    """
    Log the full exception traceback when an exception occurs.
    Should be called within an except block.
    """
    exc_info = sys.exc_info()
    if exc_info[0] is not None:  # If there's an active exception
        exc_trace = "".join(traceback.format_exception(*exc_info))
        logger.error(f"Exception traceback:\n{exc_trace}")


@r.post("")
@limiter.limit("10/minute")
async def chat(
    request: Request,
    data: ChatData,
    api_key: str = Depends(verify_api_key),
):
    request_started_at = time.monotonic()
    trace: RequestTrace | None = None

    try:
        last_message_content = data.get_last_message_content()
        params = data.data if isinstance(data.data, dict) else {}
        _warn_on_client_role(params)

        session_id = request.headers.get("X-Session-ID", request.headers.get("X-Session-Id"))
        device_id = request.headers.get("X-Device-ID")

        # Security validation - primary defense with contextual responses
        is_suspicious, blocked_message, security_details = await InputValidator.validate_input_security_async(last_message_content)

        # If input is blocked, return the security message as a normal response
        if blocked_message:
            user_language = _resolve_user_language(data, last_message_content)

            blocked_tags = chat_tags(
                language=user_language,
                security=security_tag(True, {"risk_level": security_details.get("risk_level", "UNKNOWN")}),
                session_id=session_id,
            )

            logger.warning(
                f"Security validation blocked suspicious input - "
                f"Risk: {security_details.get('risk_level', 'UNKNOWN')}, "
                f"Reason: {security_details.get('reason', 'unknown')}"
            )

            trace = RequestTrace(
                "chat",
                input=last_message_content,
                user_id=device_id,  # device fingerprint as the Langfuse user
                session_id=session_id,
                tags=blocked_tags,
                metadata={
                    "security_validation": {
                        "blocked": True,
                        "risk_level": security_details.get("risk_level", "UNKNOWN"),
                        "reason": security_details.get("reason", "security_validation_failed"),
                        "details": security_details
                    },
                    "user_language": user_language,
                    **base_metadata(),
                },
            )
            trace.finish(
                output=blocked_message,
                level="WARNING",
                status_message=f"Blocked: {security_details.get('reason', 'security_validation_failed')}",
            )

            return VercelStreamResponse(
                request,
                EventCallbackHandler(
                    language=LocalizationManager.detect_language(last_message_content)
                ),
                _StaticResponse(blocked_message),
                data,
                trace_id=trace.trace_id,
                skip_suggestions=True,
                user_language=user_language,
                emit_initial_status=False,
            )

        # Sanitize allowed input as additional protection
        if is_suspicious and security_details.get("risk_level") == "LOW":
            last_message_content = InputValidator.sanitize_input(last_message_content)

        # Get the conversation history from incoming messages
        messages = data.get_history_messages()

        # Resolve languages from what the user TYPED, before the English
        # edited-draft scaffolding below is appended to the turn.
        typed_message = last_message_content
        user_language, language_from_settings = _resolve_language(data, typed_message)

        # The user can type straight into the rendered draft, and those edits
        # live only in the browser DOM — the history below still holds the draft
        # as the MODEL wrote it. Append the user's version to this turn so the
        # next revision starts from what they actually have in front of them.
        #
        # Screened separately: this content arrives AFTER
        # validate_input_security_async has already run on the message, so
        # without this it would reach the model unscreened. A suspicious draft is
        # DROPPED, not blocked — the user's actual question still deserves an
        # answer, and the model is told it cannot see their edits.
        _draft_text = extract_draft_text(params)
        if _draft_text:
            _d_suspicious, _, _d_details = (
                await InputValidator.validate_input_security_async(_draft_text)
            )
            if _d_suspicious and _d_details.get("risk_level") != "LOW":
                logger.warning(
                    "[draft_context] dropped edited draft, risk_level=%s",
                    _d_details.get("risk_level"),
                )
                last_message_content = f"{last_message_content}{build_dropped_draft_notice()}"
            else:
                last_message_content = (
                    f"{last_message_content}{build_edited_draft_context(params)}"
                )

        # Pinned on the server: no client input takes part in the filter.
        filters = instructor_filters()

        user_timezone = request.headers.get("X-Timezone", "UTC")

        success_tags = chat_tags(
            language=user_language,
            security=security_tag(is_suspicious, security_details),
            session_id=session_id,
        )

        security_metadata = {
            "input_validated": True,
            "is_suspicious": is_suspicious,
            "risk_level": security_details.get("risk_level", "NONE") if is_suspicious else "NONE"
        }
        if is_suspicious:
            security_metadata["details"] = security_details

        clean_metadata = {
            "security_validation": security_metadata,
            "user_language": user_language,
            **base_metadata(),
        }
        answer_nodes: list[Any] = []
        answer_completed = [False]  # set once the orchestrator returns an answer

        # The root of this request's trace. It stays open while the answer
        # streams; the orchestrator and suggestions attach to it later.
        trace = RequestTrace(
            "chat",
            input=last_message_content,
            user_id=device_id,  # device fingerprint as the Langfuse user
            session_id=session_id,
            tags=success_tags,
            metadata=clean_metadata,
        )
        trace_id = trace.trace_id

        # The pipeline status indicator follows the language the user
        # PROMPTED in (pure text detection — not the app UI-language pref).
        event_handler = EventCallbackHandler(
            language=LocalizationManager.detect_language(typed_message)
        )
        retrieval_metadata: dict[str, Any] = {}
        orchestrator = RetrievalOrchestrator()

        async def _on_stream_end(final_response: str) -> None:
            # Update trace output after streaming finishes (or client disconnects).
            # Read here, not after run() returns: a leak must reach the trace
            # even when the answer then fails.
            late_tags: list[str] = []
            try:
                if orchestrator.audience_leak_dropped:
                    # Should never happen: the filter already excludes these. A
                    # finding, so it is tagged for a dashboard filter, not hidden.
                    late_tags.append(AUDIENCE_LEAK_TAG)
                    retrieval_metadata["audience_leak_dropped"] = orchestrator.audience_leak_dropped
                retrieval_metadata["login_links"] = orchestrator.login_links
                retrieval_metadata["login_links_labeled"] = orchestrator.login_links_labeled
                clean_metadata.update(
                    answer_metadata(final_response, answer_nodes, completed=answer_completed[0])
                )
                if retrieval_metadata:
                    clean_metadata.update(retrieval_metadata)
                clean_metadata["latency"] = {
                    "total_duration_ms": round((time.monotonic() - request_started_at) * 1000),
                }
            except Exception as metadata_error:
                logger.error(f"Failed to build Langfuse trace metadata: {metadata_error}")
            finally:
                # Always close the trace: an un-ended root is never exported.
                # WARNING when no answer came back (failure, timeout, disconnect);
                # the orchestrator's own span carries the error itself.
                trace.finish(
                    output=final_response,
                    metadata=clean_metadata,
                    extra_tags=late_tags,
                    level="ERROR" if late_tags else (None if answer_completed[0] else "WARNING"),
                    status_message=None if answer_completed[0] else "answer not completed",
                )

        async def _get_response() -> Any:
            logger.info(f"Creating chat engine with filters: {filters}")
            # This runs inside the SSE generator, after the handler returned, so
            # attach the orchestrator span (and the LLM calls under it) to the
            # request's trace explicitly.
            with trace.propagate():
                response = await orchestrator.run(
                    last_message_content,
                    messages,
                    filters=filters,
                    params=params,
                    timezone=user_timezone,
                    event_handler=event_handler,
                    user_language=user_language,
                    answer_language=user_language if language_from_settings else None,
                    **trace.child_kwargs(),
                )
            answer_nodes.extend(getattr(response, "source_nodes", None) or [])
            answer_completed[0] = True
            try:
                retrieval_metadata.update(
                    {
                        "retrieved_docs": "\n\n".join(
                            f"node_id: {idx+1}\n{node.metadata.get('url', '')}\n{node.text}"
                            for idx, node in enumerate(response.source_nodes)
                        ),
                        "retrieved_docs_count": len(response.source_nodes),
                    }
                )
            except Exception as retrieval_error:
                logger.error(f"Failed to build retrieved docs metadata: {retrieval_error}")
            return response

        return VercelStreamResponse(
            request,
            event_handler,
            _get_response(),
            data,
            trace_id=trace_id,
            trace=trace,
            user_language=user_language,
            skip_suggestions=is_suspicious,
            on_stream_end=_on_stream_end,
        )
    except Exception as e:
        logger.exception("Error in chat engine", exc_info=True)
        _log_exception_trace()

        # Track exception in Langfuse with ERROR level
        try:
            if trace is not None:
                trace.finish(output=None, level="ERROR", status_message=f"Exception: {type(e).__name__}")
        except Exception as langfuse_error:
            logger.error(f"Failed to update Langfuse with error: {langfuse_error}")

        # Fail safe: only leak internal error details when dev is EXPLICITLY set.
        is_dev = os.getenv("ENVIRONMENT") == "dev"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in chat engine: {e}" if is_dev else "An error occurred. Please try again.",
        ) from e


@r.post("/draft/edit")
@limiter.limit("20/minute")
async def draft_edit(
    request: Request,
    edit_data: DraftEditRequest,
    api_key: str = Depends(verify_api_key),
) -> DraftEditResponse:
    """
    Rewrite selected draft text using the backend LLM with security validation.
    """
    instruction = edit_data.instruction
    session_id = request.headers.get("X-Session-ID", request.headers.get("X-Session-Id"))
    device_id = request.headers.get("X-Device-ID")
    draft_type = edit_data.draft_type
    selected_text_length = len(edit_data.selected_text or "")
    full_content_length = len(edit_data.full_content or "")
    subject_length = len((edit_data.subject or "").strip())

    def _record_draft_edit_trace(
        *,
        outcome: str,
        terminal_reason: str,
        observed_input: str,
        observed_output: str,
        level: str,
        status_message: str,
        security_is_suspicious: bool,
        security_risk_level: str,
        security_details_payload: dict,
        extra_metadata: Optional[dict] = None,
    ) -> None:
        metadata = {
            "security_validation": {
                "is_suspicious": security_is_suspicious,
                "risk_level": security_risk_level,
                "details": security_details_payload,
            },
            "draft_edit": {
                "outcome": outcome,
                "terminal_reason": terminal_reason,
                "draft_type": draft_type,
                "selected_text_length": selected_text_length,
                "instruction_length": len(observed_input or ""),
                "full_content_length": full_content_length,
                "subject_length": subject_length,
            },
        }
        if extra_metadata:
            metadata["draft_edit"].update(extra_metadata)

        try:
            trace.finish(
                output=observed_output,
                metadata=metadata,
                extra_tags=[f"outcome:{outcome}"],
                level=level,
                status_message=status_message,
            )
        except Exception as trace_error:
            logger.warning("Failed to record Langfuse draft edit trace: %s", trace_error)

    is_suspicious, blocked_message, security_details = await InputValidator.validate_input_security_async(
        instruction
    )

    security_risk_level = (
        security_details.get("risk_level", "UNKNOWN")
        if is_suspicious
        else "NONE"
    )

    # What the model will actually see: sanitized when the screen rated it LOW.
    safe_instruction = instruction
    if is_suspicious and security_details.get("risk_level") == "LOW":
        safe_instruction = InputValidator.sanitize_input(instruction)

    # The trace starts once the security result is known; the rewrite call
    # nests under it, and the outcome tag is added when it finishes. Its input
    # is what the model saw (the raw instruction only when it was blocked).
    trace = RequestTrace(
        "draft_edit",
        input=instruction if blocked_message else safe_instruction,
        user_id=device_id,
        session_id=session_id,
        tags=[
            *identity_tags(),
            "feature:draft-edit",
            f"draft_type:{draft_type}",
            "source:draft-edit",
            security_tag(is_suspicious, {"risk_level": security_risk_level}),
        ],
        metadata={"draft_type": draft_type},
    )

    if blocked_message:
        logger.warning(
            "Draft edit blocked by security validation - risk=%s reason=%s",
            security_details.get("risk_level", "UNKNOWN"),
            security_details.get("reason", "unknown"),
        )
        _record_draft_edit_trace(
            outcome="security_blocked",
            terminal_reason=security_details.get("reason", "security_validation_failed"),
            observed_input=instruction,
            observed_output=blocked_message,
            level="WARNING",
            status_message="Draft edit blocked by security validation",
            security_is_suspicious=True,
            security_risk_level=security_details.get("risk_level", "UNKNOWN"),
            security_details_payload=security_details,
        )
        return DraftEditResponse(
            edited_text=None,
            blocked=True,
            message=blocked_message,
            reason="security_validation_failed",
        )

    try:
        with trace.propagate():
            edited_text, rejection_reason, rewrite_telemetry = await rewrite_selected_text_with_llm(
                draft_type=edit_data.draft_type,
                instruction=safe_instruction,
                selected_text=edit_data.selected_text,
                full_content=edit_data.full_content,
                subject=edit_data.subject,
                **trace.child_kwargs(),
            )
    except Exception as exc:
        # Close the trace (an un-ended root is never exported), then fail as before.
        trace.finish(output=None, level="ERROR", status_message=f"Draft edit failed: {type(exc).__name__}")
        raise

    if not edited_text:
        terminal_reason = str(rewrite_telemetry.get("terminal_reason", "model_rejected"))
        # The LLM's __NO_EDIT__ sentinel is now the sole supportability decision
        # (the English-keyword regex gate that used to precede the LLM was
        # removed in this refactor). When the LLM judges the instruction is not
        # a genuine edit request, the response `reason` is deliberately kept as
        # "invalid_edit_instruction" so existing Langfuse dashboards built on
        # that value stay intact; the distinct internal `terminal_reason`
        # ("model_no_edit") carries the real cause now that the mechanism
        # changed from a regex gate to an LLM judgment.
        is_unsupported_instruction = terminal_reason in (
            "model_no_edit",
            "instruction_missing",
        )
        if terminal_reason == "model_exception":
            outcome = "model_exception"
        elif is_unsupported_instruction:
            outcome = "invalid_instruction"
        else:
            outcome = "model_rejected"
        rejection_message = rejection_reason or "Unable to apply that edit. Please try again."

        _record_draft_edit_trace(
            outcome=outcome,
            terminal_reason=terminal_reason,
            observed_input=safe_instruction,
            observed_output=rejection_message,
            level="ERROR" if outcome == "model_exception" else "WARNING",
            status_message=(
                "Draft edit service exception"
                if outcome == "model_exception"
                else (
                    "Draft edit instruction rejected"
                    if outcome == "invalid_instruction"
                    else "Draft edit rejected"
                )
            ),
            security_is_suspicious=is_suspicious,
            security_risk_level=security_risk_level,
            security_details_payload=security_details if is_suspicious else {},
            extra_metadata=rewrite_telemetry,
        )

        return DraftEditResponse(
            edited_text=None,
            blocked=True,
            message=rejection_message,
            reason=(
                "invalid_edit_instruction"
                if is_unsupported_instruction
                else "edit_rejected"
            ),
        )

    _record_draft_edit_trace(
        outcome="success",
        terminal_reason="ok",
        observed_input=safe_instruction,
        observed_output=edited_text,
        level="DEFAULT",
        status_message=(
            "Draft edit generated"
            if not rewrite_telemetry.get("retry_used")
            else "Draft edit generated after retry"
        ),
        security_is_suspicious=is_suspicious,
        security_risk_level=security_risk_level,
        security_details_payload=security_details if is_suspicious else {},
        extra_metadata=rewrite_telemetry,
    )

    return DraftEditResponse(
        edited_text=edited_text,
        blocked=False,
        message=None,
        reason="ok",
    )


@r.post("/thumbs_request")
@limiter.limit("30/minute")
async def thumbs_request(
    request: Request,
    thumbs_data: ThumbsRequest,
    api_key: str = Depends(verify_api_key),
):
    trace_id = thumbs_data.trace_id
    # Normalize values for comparison, but keep a canonical "Good"/"Bad" for display consistency.
    value_raw = (thumbs_data.value or "").strip()
    value_norm = value_raw.lower()
    if value_norm == "good":
        value = "Good"
    elif value_norm == "bad":
        value = "Bad"
    elif value_norm == "":
        value = ""
    else:
        value = value_raw

    # IMPORTANT:
    # Langfuse "score" updates are upserts by `id`. If we don't explicitly send a new `comment`,
    # the previous comment can remain attached to the score. When users switch from BAD -> GOOD
    # (or clear their rating), we should clear any previously submitted comment.
    # Score comments are free text; redact them like trace inputs (§9.2).
    comment = redact(thumbs_data.comment or "")
    if value_norm != "bad":
        comment = ""
    score_id = f'{trace_id}_feedback'

    # Record the user feedback score (an upsert on score_id).
    langfuse.create_score(
        score_id=score_id,
        trace_id=trace_id,
        name="user_feedback",
        data_type="CATEGORICAL",
        value=value,
        comment=comment,
    )
    if value_norm == "bad":
        logger.info(f"Negative feedback received for trace {trace_id}")

    return {"feedback": value}


def _get_cloudinary_config() -> Tuple[str, str, str]:
    """
    Read Cloudinary config from either explicit vars or CLOUDINARY_URL.
    Supports:
      - CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
      - CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>
    """
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()

    cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
    if cloudinary_url and (not cloud_name or not api_key or not api_secret):
        parsed = urlparse(cloudinary_url)
        if parsed.scheme == "cloudinary":
            cloud_name = cloud_name or (parsed.hostname or "")
            api_key = api_key or (parsed.username or "")
            api_secret = api_secret or (parsed.password or "")

    return cloud_name, api_key, api_secret


async def _upload_screenshot_to_cloudinary(file: UploadFile) -> str:
    cloud_name, api_key, api_secret = _get_cloudinary_config()
    if not cloud_name or not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Screenshot uploads are not configured",
        )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Screenshot must be an image file",
        )

    # Read bytes once (we need them both for size validation and upload).
    content = await file.read()
    max_bytes = 10 * 1024 * 1024  # 10MB
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Screenshot too large (max 10MB)",
        )

    folder = "instructor-assistant/feedback"
    timestamp = int(time.time())

    # Cloudinary signature: sha1(sorted_params + api_secret)
    params = {"folder": folder, "timestamp": timestamp}
    signature_base = "&".join(f"{k}={params[k]}" for k in sorted(params))
    signature = hashlib.sha1((signature_base + api_secret).encode("utf-8")).hexdigest()

    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    data = {
        "api_key": api_key,
        "timestamp": str(timestamp),
        "signature": signature,
        "folder": folder,
    }
    files = {
        "file": (
            file.filename or "screenshot",
            content,
            file.content_type or "application/octet-stream",
        )
    }

    client = get_http_client()
    resp = await client.post(url, data=data, files=files)
    if resp.status_code >= 400:
        logger.error(
            "Cloudinary upload failed (%s): %s",
            resp.status_code,
            resp.text[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Screenshot upload failed",
        )

    payload = resp.json()
    screenshot_url = payload.get("secure_url") or payload.get("url") or ""
    if not screenshot_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Screenshot upload failed",
        )
    return screenshot_url


@r.post("/feedback/general")
@limiter.limit("5/minute")
async def general_feedback(
    request: Request,
    feedback: str = Form(...),
    screenshot: Optional[UploadFile] = File(None),
    api_key: str = Depends(verify_api_key),
):
    """
    General user feedback not tied to a specific chat message.
    Optionally accepts a screenshot image which is stored in Cloudinary.
    """
    feedback_text = (feedback or "").strip()
    if not feedback_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="feedback is required",
        )

    session_id = request.headers.get("X-Session-ID", request.headers.get("X-Session-Id"))
    device_id = request.headers.get("X-Device-ID")

    screenshot_url = None
    if screenshot is not None:
        screenshot_url = await _upload_screenshot_to_cloudinary(screenshot)

    # Log to Langfuse as a standalone trace for later filtering and review.
    RequestTrace(
        "general_feedback",
        input=feedback_text,
        user_id=device_id,
        session_id=session_id,
        tags=[*identity_tags(), "feedback", "general"],
        metadata={"screenshot_url": screenshot_url, "role": INSTRUCTOR_ROLE},
    ).finish(output=None)

    return {"status": "success", "message": "Thank you for your feedback!"}
