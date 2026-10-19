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
