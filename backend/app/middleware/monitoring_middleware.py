"""
Request middleware: a request ID per request (log filter + X-Request-ID
header), benign client disconnects finished as 499, and loud crash logging.

Upstream also fed an S3 metrics collector (app.monitoring) from here. That
service was never started upstream and is not ported; Langfuse and Sentry
cover observability.
"""

import uuid
import sys
import traceback
import psutil
from contextvars import ContextVar
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from anyio import EndOfStream
import logging

logger = logging.getLogger("uvicorn")

# Stores the active request ID for the current async context.
# Default "-" means "no active request" (e.g. startup logs).
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """Injects the current request_id into every log record it touches."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def _is_client_disconnect(exc: BaseException) -> bool:
    """True when ``exc`` means the client went away before we could respond.

    Two benign signatures (tab close, refresh, navigation, network drop):
      * ``starlette.requests.ClientDisconnect`` — raised while reading the body.
      * ``RuntimeError("No response returned.")`` whose ``__context__`` is
        ``anyio.EndOfStream`` — what ``BaseHTTPMiddleware`` raises when the
        downstream task ends without sending a response, i.e. a streaming
        response cut short by a disconnect before the first byte. Requiring the
        ``EndOfStream`` context keeps a genuine "produced no response" BUG from
        being misclassified as benign.
    """
    if isinstance(exc, ClientDisconnect):
        return True
    return (
        isinstance(exc, RuntimeError)
        and str(exc) == "No response returned."
        and isinstance(exc.__context__, EndOfStream)
    )


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware that tags every HTTP request with an ID and classifies failures."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID and bind it to the current async context
        request_id = str(uuid.uuid4())
        token = request_id_ctx.set(request_id)

        # LoggerAdapter so every log from this middleware carries request_id
        log = logging.LoggerAdapter(logger, {"request_id": request_id})

        # Extract request info
        endpoint = request.url.path
        method = request.method
        client_ip = self._get_client_ip(request)

        try:
            # Process request
            response = await call_next(request)

            # Add response headers for tracing
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Classify before we shout. A client that vanished before we could
            # respond is BENIGN (tab close, refresh, navigation, network drop):
            # log it quietly and finish as 499 ("client closed request") so it
            # cannot masquerade as a 500/server crash in the logs, in Sentry, or
            # in the error metrics. Anything else is a REAL failure and stays
            # LOUD at ERROR with full crash context (memory + traceback) so a
            # genuine problem is never hidden.
            if _is_client_disconnect(e):
                log.warning(
                    f"Client disconnected before the response completed "
                    f"({method} {endpoint}, client={client_ip}, "
                    f"signature={type(e).__name__}) — benign, no server error."
                )
                return Response(status_code=499)

            error = str(e)

            # Enhanced error context for crash diagnosis
            error_context = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            }

            # Capture memory state at crash time
            try:
                process = psutil.Process()
                mem_info = process.memory_info()
                error_context.update({
                    "crash_memory_rss_mb": mem_info.rss / 1024 / 1024,
                    "crash_memory_vms_mb": mem_info.vms / 1024 / 1024,
                    "crash_memory_percent": process.memory_percent(),
                    "crash_num_threads": process.num_threads(),
                })
            except Exception as mem_error:
                log.warning(f"Could not capture crash memory state: {mem_error}")

            log.error(
                f"Request crashed: {error_context['error_type']} - {error}\n"
                f"Memory at crash: {error_context.get('crash_memory_rss_mb', 'N/A')} MB\n"
                f"Traceback:\n{error_context['traceback']}"
            )
            raise

        finally:
            request_id_ctx.reset(token)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP from headers (handles proxies/load balancers)."""
        # Check X-Forwarded-For header first (set by proxies/load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, get the first (original client)
            return forwarded_for.split(",")[0].strip()
        
        # Fallback to direct client host
        return request.client.host if request.client else "unknown"
