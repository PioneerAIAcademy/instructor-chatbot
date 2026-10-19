"""Tests for `normalize_rtf_draft` — the deterministic guarantee that an
`rtf`-route answer comes back as a correctly-fenced, citation-clean draft so
the frontend always mounts DraftComposer.

See ROOT_CAUSE.md §3 (primary layer). The helper does ONLY mechanical text
work — fence wrapping + [^N] marker relocation — acting on the supervisor's
reliable structured route flag, never a regex semantic gate.
"""

from app.engine.draft_normalizer import normalize_rtf_draft


# --- fencing an un-fenced draft -------------------------------------------

def test_wraps_unfenced_draft_in_message_fence():
    """An un-fenced draft body gets a ```message``` fence so the frontend's
    inferDraftTypeFromBlock can mount DraftComposer."""
    text = "Hello [Student Name],\n\nYour block starts Monday.\n\nBest,\n[Your Name]"
    out = normalize_rtf_draft(text, "message")
    assert out.startswith("```message\n")
    assert out.rstrip().endswith("```")
    # The whole draft body is preserved inside the fence.
    assert "Hello [Student Name]," in out
    assert "Your block starts Monday." in out
    assert "[Your Name]" in out


def test_wraps_unfenced_draft_in_email_fence_when_draft_kind_email():
    """draft_kind drives the fence tag — email yields ```email```."""
    text = "Subject: Reminder\n\nHello [Student Name],\n\nSee you Monday.\n\nBest,\n[Your Name]"
    out = normalize_rtf_draft(text, "email")
    assert out.startswith("```email\n")
    assert out.rstrip().endswith("```")


def test_draft_kind_none_falls_back_to_message():
    """When draft_kind is None (older model output / safe-default plan), the
    normalizer uses the conservative 'message' fence."""
    out = normalize_rtf_draft("Hi there, see you Monday.", None)
    assert out.startswith("```message\n")


def test_draft_kind_junk_value_falls_back_to_message():
    """A junk draft_kind string (not 'email'/'message') falls back to
    'message' — consistent with the schema's clamp-to-None behavior."""
    out = normalize_rtf_draft("Hi there, see you Monday.", "whatsapp")
    assert out.startswith("```message\n")


# --- idempotency ----------------------------------------------------------

def test_idempotent_on_already_fenced_message_draft():
    """An already-correctly-fenced draft passes through unchanged — the
    helper must be idempotent (running it twice yields the same result)."""
    text = "```message\nHello [Student Name],\n\nSee you Monday.\n\nBest,\n[Your Name]\n```"
    once = normalize_rtf_draft(text, "message")
    twice = normalize_rtf_draft(once, "message")
    assert once == twice


def test_idempotent_on_already_fenced_draft_with_external_citation():
    """A fully-correct draft (fence + citation already outside) is unchanged."""
    text = (
        "```email\n"
        "Subject: Reminder\n\n"
        "Hello [Student Name],\n\n"
        "Your block starts Monday.\n\n"
        "Best,\n[Your Name]\n"
        "```\n\n"
        "[^1]"
    )
    out = normalize_rtf_draft(text, "message")
    assert out == text


def test_already_fenced_email_kept_even_when_draft_kind_says_message():
    """If the model already produced a valid ```email``` fence, the existing
    tag wins — the normalizer does not downgrade it to draft_kind's value."""
    text = "```email\nSubject: Hi\n\nHello [Student Name],\n\nBody.\n\nBest,\n[Your Name]\n```"
    out = normalize_rtf_draft(text, "message")
    assert "```email" in out
    assert "```message" not in out


# --- citation hoisting + de-duplication -----------------------------------

def test_hoists_and_dedupes_citations_outside_unfenced_draft():
    """[^N] markers inside an un-fenced draft are stripped from the body and
    re-emitted, de-duplicated, on one line after the closing fence."""
    text = (
        "Hello [Student Name], [^1]\n\n"
        "Your block starts Monday! [^1]\n\n"
        "Best,\n[Your Name] [^1]"
    )
    out = normalize_rtf_draft(text, "message")
    fence_open = out.index("```message")
    fence_close = out.index("```", fence_open + 3)
    body = out[fence_open:fence_close]
    after = out[fence_close + 3:]
    # No citation marker survives inside the fenced draft body.
    assert "[^" not in body
    # Citation is hoisted out and de-duplicated to a single [^1].
    assert out.count("[^1]") == 1
    assert "[^1]" in after


def test_hoists_citations_out_of_already_fenced_draft():
    """When the model fenced the draft but left [^N] markers INSIDE it
    (exactly the grounding-guard behavior), they are hoisted out."""
    text = (
        "```message\n"
        "Hello [Student Name], [^2]\n\n"
        "Your block starts Monday. [^2]\n\n"
        "Best,\n[Your Name]\n"
        "```"
    )
    out = normalize_rtf_draft(text, "message")
    fence_open = out.index("```message")
    fence_close = out.index("```", fence_open + 3)
    body = out[fence_open:fence_close]
    after = out[fence_close + 3:]
    assert "[^" not in body
    assert out.count("[^2]") == 1
    assert "[^2]" in after


def test_multiple_distinct_citations_all_hoisted_in_order():
    """Distinct citation numbers are all hoisted, order-preserved, deduped."""
    text = "Hello, [^1] block info [^3] and more. [^1] [^3]"
    out = normalize_rtf_draft(text, "message")
    fence_close = out.rindex("```")
    after = out[fence_close + 3:].strip()
    assert after == "[^1] [^3]"
    body = out[: fence_close]
    assert "[^" not in body.split("```message")[1]


def test_no_citations_means_no_trailing_citation_line():
    """A draft with no [^N] markers gets a fence and nothing else after it."""
    out = normalize_rtf_draft("Hello [Student Name], see you Monday.", "message")
    assert out == "```message\nHello [Student Name], see you Monday.\n```"


# --- edge cases -----------------------------------------------------------

def test_empty_text_returns_unchanged():
    assert normalize_rtf_draft("", "message") == ""
    assert normalize_rtf_draft("   \n  ", "message") == "   \n  "


def test_unwraps_non_draft_fence_and_re_fences():
    """If the model wrapped the draft in a plain ```/```text fence instead of
    a draft fence, the body is unwrapped and re-fenced with the draft tag —
    no nested fences."""
    text = "```\nHello [Student Name],\n\nSee you Monday.\n```"
    out = normalize_rtf_draft(text, "message")
    assert out.startswith("```message\n")
    # Exactly two fence delimiters — one open, one close, no nesting.
    assert out.count("```") == 2


# --- extract_draft_core (presenter wrapper helper) ------------------------

def test_extract_draft_core_drops_surrounding_prose():
    """The presenter supplies its own framing, so extract_draft_core must keep
    ONLY the fenced draft + hoisted citations and drop the synthesis lead-in
    (otherwise the pre_card duplicates it — the email-draft duplicate bug)."""
    from app.engine.draft_normalizer import extract_draft_core

    normalized = (
        "Here's an email draft reminding your students to submit on Canvas:\n\n"
        "```email\nSubject: Reminder\n\nHello [Student Name], submit on Canvas.\n```\n\n"
        "[^1] [^2]\n\nSome trailing note."
    )
    core = extract_draft_core(normalized)
    assert core is not None
    assert core.startswith("```email\n")
    assert "Here's an email draft" not in core  # synthesis lead-in dropped
    assert "Some trailing note" not in core      # trailing prose dropped
    assert core.rstrip().endswith("[^1] [^2]")   # citations preserved after fence


def test_extract_draft_core_no_fence_returns_none():
    from app.engine.draft_normalizer import extract_draft_core
    assert extract_draft_core("just some prose, no fence") is None
    assert extract_draft_core("") is None


def test_extract_draft_core_no_citations():
    from app.engine.draft_normalizer import extract_draft_core
    normalized = "```message\nHello, see you Monday.\n```"
    assert extract_draft_core(normalized) == "```message\nHello, see you Monday.\n```"


# --- markdown heading strip (2026-06-13) ----------------------------------

def test_strips_markdown_headings_from_unfenced_draft():
    """`### Overview` leaked the literal `###` into the DraftComposer body
    (rendered as plain text). Headings belong in neither an email nor a
    message — the marker is stripped, the heading text kept as a plain line."""
    text = (
        "Dear Students,\n\n"
        "### Overview of BYU-Pathway\n"
        "BYU-Pathway provides accessible higher education.\n\n"
        "## PathwayConnect Program\n"
        "It includes PC 101, PC 102, and PC 103.\n\n"
        "Best,\n[Your Name]"
    )
    out = normalize_rtf_draft(text, "email")
    assert "###" not in out
    assert "## " not in out
    # heading TEXT is preserved as a plain line
    assert "Overview of BYU-Pathway" in out
    assert "PathwayConnect Program" in out
    assert out.startswith("```email\n")


def test_strips_markdown_headings_inside_already_fenced_draft():
    text = "```email\nDear Students,\n\n### Section One\nBody text here.\n```"
    out = normalize_rtf_draft(text, "email")
    assert "###" not in out
    assert "Section One" in out
    assert "Body text here." in out


def test_heading_strip_leaves_inline_whatsapp_emphasis_untouched():
    """A message's intentional inline *bold* / _italic_ is NOT a line-leading
    heading and must survive (line-leading-only match)."""
    text = "```message\nHey [Student Name], *don't* forget the _gathering_ tonight!\n```"
    out = normalize_rtf_draft(text, "message")
    assert "*don't*" in out
    assert "_gathering_" in out


def test_heading_strip_does_not_touch_csharp_hash_mid_line():
    """Only line-leading `#` runs are stripped; a `#` mid-sentence stays."""
    text = "```message\nUse the C# guide and tag #pathway in your post.\n```"
    out = normalize_rtf_draft(text, "message")
    assert "C#" in out
    assert "#pathway" in out


# --- hoist_draft_citations (classic path) -------------------------------------

from app.engine.draft_normalizer import hoist_draft_citations  # noqa: E402


def test_hoist_moves_markers_out_of_message_fence_only():
    text = (
        "Use the welcome guide [^1].\n\n"
        "```message\nHi [Student Name] [^2], welcome! [^2] [^3]\n```\n\n"
        "Send it in Week 01 [^1]."
    )
    out = hoist_draft_citations(text)
    assert "```message\nHi [Student Name], welcome!\n```\n\n[^2] [^3]" in out
    assert out.startswith("Use the welcome guide [^1].")
    assert out.endswith("Send it in Week 01 [^1].")


def test_hoist_leaves_other_fences_and_clean_drafts_alone():
    code = "```python\nx = 1  # [^1]\n```"
    assert hoist_draft_citations(code) == code
    clean = "```email\nSubject: Welcome\n\nHi [Student Name],\n```"
    assert hoist_draft_citations(clean) == clean


def test_hoist_is_idempotent():
    text = "```message\nHello [^1]\n```"
    once = hoist_draft_citations(text)
    assert hoist_draft_citations(once) == once


def test_hoist_uses_the_shared_fence_rules():
    # An inline ```message``` span isn't a fence, so nothing in it is hoisted.
    inline = "Use ```message``` blocks for drafts [^1]."
    assert hoist_draft_citations(inline) == inline
    # An unclosed fence isn't a fence either.
    unclosed = "```message\nHi [^1]\nno closing line"
    assert hoist_draft_citations(unclosed) == unclosed
