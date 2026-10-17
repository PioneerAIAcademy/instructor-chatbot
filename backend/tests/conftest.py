"""Pytest fixtures and configuration for backend tests."""

import sys
from unittest.mock import Mock, MagicMock

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
