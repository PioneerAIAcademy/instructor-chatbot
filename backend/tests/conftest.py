"""Pytest fixtures and configuration for backend tests."""

import os
import sys
from unittest.mock import Mock, MagicMock

# Keep the suite off the network. The security tests call InputValidator,
# which tries to load pytector's Hugging Face model on every call (it never
# loads with the pinned torch; see CLAUDE.md §14). Offline, that attempt
# fails at once instead of making a Hub request, so the result is the same
# (no ML detector) and the tests stop depending on Hugging Face.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Tests must never send anything to Langfuse. app/langfuse.py calls
# load_dotenv(), which would otherwise pick up real keys from backend/.env on a
# developer machine. load_dotenv() never overrides a variable that's already
# set, so blank keys here keep the client disabled (every call a no-op).
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

# Mock Voyage AI client at import time (before app.engine is imported)
# This allows tests that don't need RAG/vector search to run without VOYAGE_API_KEY
if "voyageai" not in sys.modules:
    mock_voyage_module = MagicMock()
    mock_voyage_module.Client = MagicMock(return_value=MagicMock())
    mock_voyage_module.error = MagicMock()
    sys.modules["voyageai"] = mock_voyage_module
    sys.modules["voyageai.client"] = MagicMock()
    sys.modules["voyageai._base"] = MagicMock()
    sys.modules["voyageai.error"] = MagicMock()


# --- a recording stand-in for app.api.tracing.RequestTrace --------------------------

import contextlib  # noqa: E402

import pytest  # noqa: E402


class FakeTrace:
    """Records what a RequestTrace is given, without Langfuse."""

    def __init__(self, name, *, input, user_id, session_id, tags, metadata):
        self.name = name
        self.input = input
        self.user_id = user_id
        self.session_id = session_id
        self.tags = list(tags)
        self.metadata = metadata
        self.finished = None
        self.trace_id = f"trace-{name}"

    def child_kwargs(self):
        return {}

    @contextlib.contextmanager
    def propagate(self):
        yield

    def finish(self, **kwargs):
        if self.finished is None:
            self.finished = kwargs

    @property
    def all_tags(self):
        """Tags at start plus any added when the trace finished."""
        return self.tags + list((self.finished or {}).get("extra_tags") or [])


@pytest.fixture
def fake_traces(monkeypatch):
    """Replace RequestTrace in the chat router; returns the list of traces made."""
    from app.api.routers import chat as chat_module

    made = []

    def _make(*args, **kwargs):
        trace = FakeTrace(*args, **kwargs)
        made.append(trace)
        return trace

    monkeypatch.setattr(chat_module, "RequestTrace", _make)
    return made
