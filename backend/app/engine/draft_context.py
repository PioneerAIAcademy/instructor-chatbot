"""Carry the user's edited RTF draft into the turn the model actually sees.

WHY. The draft is rendered in a `contentEditable` widget, so a user can type
straight into it — but those edits live only in the browser DOM. The message
history the model receives still holds the draft as *it* wrote it. Before this
module the model had no way to know the user had changed anything.

The measured failure (Langfuse session `6d05f93d`, 2026-08-19): asked to "review
the slight changes I have made so far", the model returned a confident
three-point review of edits it had never received, reconstructed out of the
user's own earlier *request* text. It read as genuine, which is what made it
harmful — the user believed their edits had landed, and replied "You removed my
adjustments." A silent no-op would have done less damage than a plausible
fabrication.

WHY A PROMPT BLOCK AND NOT A DIFF. Reconciling the user's version with the
model's last version is exactly the kind of string surgery that has burned this
codebase before (see the quote-strip guard that deleted real answers). The model
is better at "here is the current text, revise it" than any patcher we would
write, so this hands over the draft and states the ground rules beside it.

WHY THE INSTRUCTION SITS *NEXT TO* THE DRAFT. Proven repeatedly on gpt-4o-mini:
where a rule sits beats how forcefully it is worded. A rule 2,000 words away in
the system prompt loses behind chat history; the same rule adjacent to the text
it governs holds. So the "work from THIS text" and "do not describe changes you
cannot see" clauses are wrapped around the draft itself rather than added to
`SYSTEM_CITATION_PROMPT`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("uvicorn")

# Matches the ceiling `DraftEditRequest.full_content` already accepts, so the two
# draft paths cannot disagree about what is too big to handle.
MAX_DRAFT_BYTES = 12 * 1024


def _clip(value: Any, limit: int = MAX_DRAFT_BYTES) -> str:
    """Coerce to a stripped string, byte-bounded on a character boundary."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


def extract_draft_text(params: Any) -> str:
    """The user's draft as plain text, for security screening.

    Separate from `build_edited_draft_context` so the caller screens the *user's*
    content without also feeding our own instruction wrapper to the validator —
    that wrapper contains the bracket characters the sanitiser strips, so
    screening the rendered block would flag our own scaffolding.
    """
    if not isinstance(params, dict):
        return ""
    draft = params.get("edited_draft")
    if not isinstance(draft, dict):
        return ""
    body = _clip(draft.get("body"))
    subject = _clip(draft.get("subject"), 2 * 1024)
    if not body and not subject:
        return ""
    return f"{subject}\n\n{body}".strip()


def build_edited_draft_context(params: Any) -> str:
    """Render the user's edited draft as a block to append to their turn.

    Returns "" whenever there is nothing to say — no draft, wrong shape, or an
    empty one. The frontend only sends `edited_draft` when the user has actually
    typed into the widget, so its presence already means "this diverged from what
    you wrote".
    """
    if not isinstance(params, dict):
        return ""

    draft = params.get("edited_draft")
    if not isinstance(draft, dict):
        return ""

    body = _clip(draft.get("body"))
    subject = _clip(draft.get("subject"), 2 * 1024)
    if not body and not subject:
        return ""

    draft_type = draft.get("draft_type")
    if draft_type not in ("email", "message"):
        draft_type = "message"

    inner = f"Subject: {subject}\n\n{body}" if subject else body

    logger.info(
        "[draft_context] attaching user-edited draft (type=%s, %d chars)",
        draft_type, len(inner),
    )

    return (
        "\n\n[The user has edited the draft since you wrote it. The text below — "
        "not any earlier version in this conversation — is the draft as it now "
        "stands in front of them. Work from THIS text: preserve their wording "
        "unless they ask you to change it. If they ask about changes that are "
        "not visible in this text, say you cannot see them and ask them to "
        "paste them, rather than describing changes you have not been given.]\n"
        f'<current_draft type="{draft_type}">\n{inner}\n</current_draft>'
    )


def build_dropped_draft_notice() -> str:
    """The note appended to the turn when the user's edited draft was screened
    out. Without it the model revises its own earlier draft as if it were the
    user's version (the same failure as session `6d05f93d`)."""
    return (
        "\n\n[The user has edited the draft since you wrote it, but their edited "
        "version could not be used, so you cannot see their edits. Say so in one "
        "short sentence and ask them to paste the text they want you to work from. "
        "Do not revise or describe the earlier version as if it were theirs.]"
    )
