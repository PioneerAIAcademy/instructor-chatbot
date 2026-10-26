"""The app's Langfuse client (langfuse 4.x, OpenTelemetry-based).

langfuse 2.x used the ingestion API that Langfuse Cloud shuts down on
2026-11-16; new organizations already can't read its data back. See
CLAUDE.md §14 (2026-10-19).

Everything sent is masked first (CLAUDE.md §9.2): `mask` covers every
observation's input, output, and metadata, including the LlamaIndex bridge's
`rag-llm` generations. Without keys the client disables itself and every call
is a no-op (offline tests rely on this).
"""

import os
import re

from dotenv import load_dotenv
from langfuse import Langfuse

from app.redaction import mask_for_langfuse
from app.version import app_version

load_dotenv()

_ZERO_ID = re.compile(r"^0+$")


def _environment() -> str | None:
    """Langfuse environment from ENVIRONMENT ("dev", "prod"): lowercase
    letters, digits, - and _, at most 40 characters, not "langfuse…"."""
    value = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if re.fullmatch(r"[a-z0-9_-]{1,40}", value) and not value.startswith("langfuse"):
        return value
    return None


langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST"),
    mask=mask_for_langfuse,
    environment=_environment(),
    release=app_version(),
)


def real_id(value: str | None) -> str | None:
    """A trace or observation ID, or None when tracing is off (the disabled
    client hands out all-zero IDs)."""
    if not value or _ZERO_ID.match(value):
        return None
    return value
