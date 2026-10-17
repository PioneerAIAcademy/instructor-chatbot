"""The user's in-place draft edits must reach the model.

Regression cover for Langfuse session `6d05f93d` (2026-08-19): a missionary
edited the RTF draft in the contentEditable widget, asked "review the slight
changes I have made so far", and got a confident three-point review of edits the
model had never received — reconstructed from the user's own earlier request
text. Nothing transmitted the edits, so nothing could have reviewed them.
"""

from app.engine.draft_context import (
    MAX_DRAFT_BYTES,
    build_edited_draft_context,
    extract_draft_text,
)


def _params(**draft):
    return {"role": "missionary", "edited_draft": draft}


# --- nothing to say -----------------------------------------------------------

def test_no_draft_produces_no_context():
    """The overwhelming majority of turns carry no draft and must be untouched."""
    assert build_edited_draft_context({"role": "missionary"}) == ""
    assert build_edited_draft_context({}) == ""


def test_malformed_params_are_ignored_rather_than_raising():
    """`data` is typed `Any` on the wire, so anything can arrive here."""
    for junk in (None, "", [], "edited_draft", 42, {"edited_draft": "a string"},
                 {"edited_draft": None}, {"edited_draft": []}):
        assert build_edited_draft_context(junk) == ""
        assert extract_draft_text(junk) == ""


def test_an_empty_draft_is_not_worth_sending():
    assert build_edited_draft_context(_params(body="   ", subject="")) == ""
    assert build_edited_draft_context(_params(body="", subject="  \n ")) == ""


# --- the draft is carried -----------------------------------------------------

def test_edited_body_reaches_the_turn():
    ctx = build_edited_draft_context(_params(draft_type="email", body="Dear all,\nWe write to you."))
    assert "Dear all,\nWe write to you." in ctx
    assert '<current_draft type="email">' in ctx
    assert "</current_draft>" in ctx


def test_subject_is_carried_and_labelled():
    ctx = build_edited_draft_context(
        _params(draft_type="email", subject="The Blessings of BYU-Pathway", body="Body here.")
    )
    assert "Subject: The Blessings of BYU-Pathway" in ctx
    assert ctx.index("Subject:") < ctx.index("Body here.")


def test_a_message_draft_has_no_subject_line():
    ctx = build_edited_draft_context(_params(draft_type="message", subject="", body="Just a note."))
    assert "Subject:" not in ctx
    assert 'type="message"' in ctx


def test_unknown_draft_type_falls_back_to_message():
    """The type is a display hint; a bad value must not drop the user's work."""
    ctx = build_edited_draft_context(_params(draft_type="pdf", body="Text."))
    assert 'type="message"' in ctx
    assert "Text." in ctx


# --- the instruction that prevents the fabrication ----------------------------

def test_the_draft_is_declared_authoritative_over_history():
    """Without this the model revises its own last version and the edits vanish."""
    ctx = build_edited_draft_context(_params(body="Edited body."))
    assert "not any earlier version" in ctx
    assert "THIS text" in ctx


def test_the_model_is_told_to_admit_what_it_cannot_see():
    """The actual defect in 6d05f93d was a fabricated review, not a lost edit."""
    ctx = build_edited_draft_context(_params(body="Edited body."))
    assert "cannot see" in ctx
    assert "rather than describing changes you have not been given" in ctx


def test_instruction_is_adjacent_to_the_draft_not_far_from_it():
    """Adjacency beats rule count on gpt-4o-mini — proven repeatedly here."""
    ctx = build_edited_draft_context(_params(body="Edited body."))
    gap = ctx.index("<current_draft") - ctx.index("cannot see")
    assert 0 < gap < 260, f"instruction drifted {gap} chars from the draft"


# --- bounds -------------------------------------------------------------------

def test_an_oversized_body_is_clipped_not_dropped():
    ctx = build_edited_draft_context(_params(body="x" * (MAX_DRAFT_BYTES + 5000)))
    assert ctx, "a long draft must still reach the model"
    assert len(ctx.encode("utf-8")) < MAX_DRAFT_BYTES + 2048


def test_clipping_does_not_split_a_multibyte_character():
    """A truncated UTF-8 sequence would raise on encode downstream."""
    ctx = build_edited_draft_context(_params(body="é" * MAX_DRAFT_BYTES))
    ctx.encode("utf-8")  # must not raise
    assert "é" in ctx


# --- the screening seam -------------------------------------------------------

def test_extract_returns_user_text_without_our_wrapper():
    """The caller screens this; feeding it our own bracketed scaffolding would
    flag characters the sanitiser strips."""
    text = extract_draft_text(_params(subject="Subj", body="Body"))
    assert text == "Subj\n\nBody"
    assert "current_draft" not in text
    assert "[" not in text


def test_extract_and_build_agree_on_emptiness():
    """The route only builds when extract found something; they must not disagree."""
    for draft in ({}, {"body": ""}, {"subject": "  "}, {"body": None}):
        assert bool(extract_draft_text(_params(**draft))) == bool(
            build_edited_draft_context(_params(**draft))
        )
