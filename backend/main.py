# flake8: noqa: E402
from dotenv import load_dotenv

load_dotenv()

import os

import sentry_sdk

# Initialize Sentry as early as possible so subsequent imports and the FastAPI
# app creation below are both covered by error tracking. FastAPI integration
# auto-enables when `fastapi` is importable, so no `integrations=[...]` is needed.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    from app.redaction import mask_for_langfuse as _mask, redact as _redact

    def _redact_breadcrumb(crumb):
        """Log lines become breadcrumbs (Sentry's logging integration) and ride
        along with later error events, so redact them as well."""
        if isinstance(crumb.get("message"), str):
            crumb["message"] = _redact(crumb["message"])
        if isinstance(crumb.get("data"), dict):
            crumb["data"] = _mask(data=crumb["data"])
        return crumb

    def _sentry_before_send(event, hint):
        """Redact emails and long digit runs in what Sentry would store:
        exception messages, the event message, log entries, and breadcrumbs
        (CLAUDE.md §9.2)."""
        for exc in (event.get("exception") or {}).get("values") or []:
            if isinstance(exc.get("value"), str):
                exc["value"] = _redact(exc["value"])
        if isinstance(event.get("message"), str):
            event["message"] = _redact(event["message"])
        logentry = event.get("logentry") or {}
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = _redact(logentry[key])
        crumbs = event.get("breadcrumbs")
        values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
        for crumb in values or []:
            if isinstance(crumb, dict):
                _redact_breadcrumb(crumb)
        return event

    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        # Do NOT capture PII (IPs, headers, request bodies) by default. Opt in
        # explicitly via SENTRY_SEND_PII=true only where privacy review allows it.
        send_default_pii=os.environ.get("SENTRY_SEND_PII", "false").lower() == "true",
        # Never attach request bodies (Sentry attaches them even with PII off)
        # or stack-frame locals (they hold the question text). §9.2.
        max_request_body_size="never",
        include_local_variables=False,
        before_send=_sentry_before_send,
        before_breadcrumb=lambda crumb, hint: _redact_breadcrumb(crumb),
        release=os.environ.get("APP_VERSION") or None,
        traces_sample_rate=1.0 if os.environ.get("ENVIRONMENT") == "dev" else 0.1,
    )

import logging
import signal

import uvicorn
from app.api.routers.chat import chat_router
from app.api.routers.chat_config import config_router
from app.api.routers.health import health_router
from app.observability import init_observability
from app.settings import init_settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

CHAT_MAX_BODY_SIZE = 512 * 1024         # 512KB for full conversation payload
FEEDBACK_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB for feedback screenshots


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only requests that carry a body need a size guard.
        if request.method in ("POST", "PUT", "PATCH"):
            path = request.url.path
            if path.startswith("/api/v1/chat/feedback"):
                limit = FEEDBACK_MAX_BODY_SIZE
                label = "10MB"
            else:
                limit = CHAT_MAX_BODY_SIZE
                label = "512KB"

            content_length = request.headers.get("content-length")
            if content_length is None:
                # No declared length (e.g. chunked transfer) — the size cannot be
                # verified cheaply, so reject rather than let it bypass the cap.
                return JSONResponse(
                    status_code=411,
                    content={"detail": "Length Required."},
                )
            try:
                size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
            if size > limit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large. Maximum size is {label}."},
                )
        return await call_next(request)

app = FastAPI(
    title="BYU-Pathway Instructor Assistant API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enforce size limits: 512KB for chat, 10MB for feedback/screenshots
app.add_middleware(RequestSizeLimitMiddleware)

init_settings()
init_observability()

# Boot guard (CLAUDE.md §7 Phase 1): refuse to start against any index that
# isn't an allowed instructor index. Raises IndexConfigError, which stops the
# process before it serves a request.
from app.engine.audience_guard import check_index_config

check_index_config()

# The Voyage client is created lazily (app/engine/custom_condense_plus_context.py),
# so check its key here: without it every rerank would fail and answers would
# silently fall back to unranked retrieval.
if not os.getenv("VOYAGE_API_KEY"):
    raise RuntimeError("VOYAGE_API_KEY is not set; the reranker needs it")

# Request IDs, 499 on client disconnect, crash logging.
from app.middleware.monitoring_middleware import MonitoringMiddleware

app.add_middleware(MonitoringMiddleware)

environment = os.getenv("ENVIRONMENT", "dev")  # Default to 'development' if not set
logger = logging.getLogger("uvicorn")

# Wildcard CORS is an explicit, dev-only opt-in — it is NOT tied to the
# default-on ENVIRONMENT value, so a deployment that forgets to set ENVIRONMENT
# still gets the restrictive origin list rather than opening to the world.
allow_all_cors = os.getenv("CORS_ALLOW_ALL", "false").lower() == "true"

if allow_all_cors:
    logger.warning("CORS_ALLOW_ALL is enabled - allowing all origins (development only)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    # Browsers send the Origin header without a trailing slash, so
    # "https://site.example/" would never match; compare without it.
    allowed_origins = [o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip().rstrip("/")]
    if not allowed_origins:
        logger.error("ALLOWED_ORIGINS is not set! CORS will block all frontend requests.")
    logger.info(f"CORS allowed origins: {allowed_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Session-ID", "X-Device-ID", "X-Timezone"],
    )

# Expose the docs redirect only in explicit dev mode (avoids advertising the API surface).
if environment == "dev":
    @app.get("/", include_in_schema=False)
    async def redirect_to_docs():
        return RedirectResponse(url="/api/docs")


app.include_router(chat_router, prefix="/api/v1/chat")
app.include_router(config_router, prefix="/api/v1/chat/config")
app.include_router(health_router, prefix="/api")


def _handle_sigterm(_signum, _frame):
    """Log SIGTERM so it appears in structured logs before Gunicorn shuts down workers."""
    logger.info("Received SIGTERM — shutting down gracefully")

signal.signal(signal.SIGTERM, _handle_sigterm)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    from app.memory_trim import start_malloc_trimmer

    start_malloc_trimmer(period_sec=300)  # return freed memory to the OS every 5 min

    # Load the prompt-injection model now, in a background thread, so the first
    # question doesn't wait for it (download + load can take ~40 s).
    from app.security.input_validator import InputValidator

    InputValidator.preload_detector_in_background()
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    from app.http_client import close_http_client
    from app.langfuse import langfuse

    await close_http_client()
    # Spans are exported in the background; send what's still queued.
    langfuse.flush()
    logger.info("Application shutdown complete")


if __name__ == "__main__":
    app_host = os.getenv("APP_HOST", "0.0.0.0")
    app_port = int(os.getenv("APP_PORT", "8000"))
    reload = True if environment == "dev" else False

    uvicorn.run(app="main:app", host=app_host, port=app_port, reload=reload)
