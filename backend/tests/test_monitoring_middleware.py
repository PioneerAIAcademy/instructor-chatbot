"""Tests for MonitoringMiddleware's classify-don't-silence error handling.

A client that disconnects before the response is sent (tab close, refresh,
navigation, network drop) must be logged as a benign WARNING and finish as 499 —
never as a 500/ERROR crash. A genuine application failure must stay LOUD at ERROR
and re-raise so it is never hidden.
"""

import asyncio
import logging

import anyio
from starlette.requests import ClientDisconnect, Request

from app.middleware.monitoring_middleware import (
    MonitoringMiddleware,
    _is_client_disconnect,
)


def _no_response_after_endofstream() -> RuntimeError:
    """Reproduce the exact prod signature: RuntimeError('No response returned.')
    whose __context__ is anyio.EndOfStream — BaseHTTPMiddleware on a streaming
    response cut short by a client disconnect before the first byte."""
    try:
        try:
            raise anyio.EndOfStream()
        except anyio.EndOfStream:
            raise RuntimeError("No response returned.")
    except RuntimeError as exc:
        return exc


class TestClientDisconnectClassification:
    def test_no_response_with_endofstream_context_is_disconnect(self):
        assert _is_client_disconnect(_no_response_after_endofstream()) is True

    def test_starlette_client_disconnect_is_disconnect(self):
        assert _is_client_disconnect(ClientDisconnect()) is True

    def test_no_response_without_endofstream_is_not_disconnect(self):
        # A genuine "produced no response" BUG (no disconnect underneath) must
        # stay a real error, not be hidden as benign.
        assert _is_client_disconnect(RuntimeError("No response returned.")) is False

    def test_unrelated_runtimeerror_is_not_disconnect(self):
        assert _is_client_disconnect(RuntimeError("boom in the engine")) is False

    def test_value_error_is_not_disconnect(self):
        assert _is_client_disconnect(ValueError("bad input")) is False


def _make_middleware() -> MonitoringMiddleware:
    # __new__ skips BaseHTTPMiddleware.__init__ (which needs a real ASGI app);
    # dispatch reads no instance state.
    return MonitoringMiddleware.__new__(MonitoringMiddleware)


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": [(b"user-agent", b"pytest"), (b"x-forwarded-for", b"1.2.3.4")],
            "client": ("1.2.3.4", 12345),
            "query_string": b"",
        }
    )


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _run_dispatch(call_next):
    """Run middleware.dispatch capturing uvicorn-logger records directly
    (independent of caplog/root propagation). Returns (response_or_None,
    raised_exc_or_None, records)."""
    logger = logging.getLogger("uvicorn")
    handler = _Capture()
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    mw = _make_middleware()

    async def run():
        return await mw.dispatch(_make_request(), call_next)

    response, raised = None, None
    try:
        response = asyncio.run(run())
    except BaseException as exc:  # noqa: BLE001 - test needs to inspect the raise
        raised = exc
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    return response, raised, handler.records


class TestDispatchClassification:
    def test_client_disconnect_logs_warning_and_returns_499(self):
        async def call_next(_request):
            raise _no_response_after_endofstream()

        response, raised, records = _run_dispatch(call_next)

        assert raised is None, "benign disconnect must not propagate"
        assert response is not None and response.status_code == 499
        assert any(
            r.levelno == logging.WARNING and "disconnect" in r.getMessage().lower()
            for r in records
        ), "expected a benign client-disconnect WARNING"
        assert not any(r.levelno >= logging.ERROR for r in records), (
            "a benign disconnect must never be logged at ERROR"
        )

    def test_real_exception_logs_error_and_reraises(self):
        async def call_next(_request):
            raise ValueError("kaboom in the chat engine")

        response, raised, records = _run_dispatch(call_next)

        assert isinstance(raised, ValueError), "real failures must re-raise"
        assert any(
            r.levelno == logging.ERROR and "crashed" in r.getMessage().lower()
            for r in records
        ), "a real failure must stay LOUD at ERROR"
