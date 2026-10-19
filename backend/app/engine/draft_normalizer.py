"""Deterministic post-processing for `rtf` (draft) route answers.

ROOT CAUSE this closes (see ROOT_CAUSE.md): a draft request routes to
`route="rtf"` correctly (the supervisor LLM's reliable structured decision),
but `_fallback_to_existing` makes `rtf` indistinguishable from `rag` — the
synthesis layer receives nothing draft-specific, so whether the draft comes
back wrapped in a ```email``` / ```message``` fence is left entirely to
gpt-4o-mini's unreliable prompt adoption (project lesson #74). An un-fenced
draft never produces a `code` node in the frontend markdown renderer, so the
interactive `DraftComposer` card never mounts.

This module's `normalize_rtf_draft()` runs ONLY on the `rtf` branch of the
orchestrator — i.e. it acts on the LLM's reliable structured route flag, NOT
on any free-text keyword scan of the answer. It is *deterministic text
mechanics* ("LLM decides, code ensures"), not a regex semantic gate:

  1. If the answer already has a valid ```email``` / ```message``` fence,
     leave the fenced block intact (the prompt's secondary layer worked) —
     only hoist citations out of it. The function is idempotent: an
     already-correct draft passes through unchanged.
  2. If there is no draft fence, wrap the draft body (the answer minus any
     trailing "Sources:" / citation-list block) in one. The fence language
     tag comes from `draft_kind` — the supervisor's structured email/message
     decision — never from a keyword scan of the body.
  3. Hoist `[^N]` citation markers OUT of the fenced block: the DRAFT
     COMPOSITION rule requires citations outside the fence, but the model and
     the grounding guards both put them inside. The de-duplicated set is
     re-emitted on a single line immediately after the closing fence. This
     is pure marker relocation, not classification.
"""

from __future__ import annotations

import re

# Fence language tags the frontend's `inferDraftTypeFromBlock` recognizes
# to mount DraftComposer (markdown.tsx). Anything else is an ordinary code
# block.
_DRAFT_FENCE_LANGS = ("email", "message")

# A fenced code block: ``` optionally followed by a language tag, then the
# body, then a closing ```. Captures (lang, body). DOTALL so the body spans
# newlines; non-greedy body so the FIRST closing fence ends the block.
_FENCED_BLOCK_RE = re.compile(
    r"```([a-zA-Z0-9_-]*)[ \t]*\n(.*?)\n?```",
    re.DOTALL,
)

# A footnote-style citation marker, e.g. [^1], [^12]. The frontend converts
# these to clickable SourceNumberButtons — DRAFT COMPOSITION requires them
# OUTSIDE the fenced draft so the composer body stays clean editable text.
_CITATION_RE = re.compile(r"\[\^(\d+)\]")


def _resolve_fence_lang(draft_kind: str | None) -> str:
    """Resolve the fence language tag from the supervisor's structured
    `draft_kind`. Falls back to "message" — the conservative default — when
    `draft_kind` is None (older model output / safe-default plan). The
    frontend's own content heuristic still upgrades a subject-bearing body
    to `email` once the body is fenced."""
    if draft_kind in _DRAFT_FENCE_LANGS:
        return draft_kind  # type: ignore[return-value]
    return "message"


def _extract_citations(text: str) -> tuple[str, list[str]]:
    """Strip every `[^N]` marker from `text` and return
    (text_without_markers, ordered_unique_marker_numbers).

    De-duplication is order-preserving (first occurrence wins) so a draft
    citing [^1] three times yields a single [^1] in the hoisted line —
    required by the PM sign-off. Whitespace left dangling where a marker
    was removed (e.g. a leading space before a newline) is collapsed so the
    cleaned draft body has no orphaned spacing.
    """
    numbers: list[str] = []
    for m in _CITATION_RE.finditer(text):
        n = m.group(1)
        if n not in numbers:
            numbers.append(n)
    stripped = _CITATION_RE.sub("", text)
    # Collapse the spacing a removed marker leaves behind: a space (or run of
    # spaces) immediately before a newline or end-of-string, and a doubled
    # space mid-line.
    stripped = re.sub(r"[ \t]+(\n|$)", r"\1", stripped)
    stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    return stripped, numbers


def _build_citation_line(numbers: list[str]) -> str:
    """Render the de-duplicated citation markers as a single line, e.g.
    `[^1] [^2]`. Empty string when there are no citations."""
    if not numbers:
        return ""
    return " ".join(f"[^{n}]" for n in numbers)


# A line-leading ATX markdown heading marker (`#`, `##`, ... up to `######`
# with optional leading indent). The DraftComposer renders the draft body as
# plain editable text (an email/message is plain prose), so a `### Heading`
# the model emits shows the literal `###` to the user (observed live). Markdown
# headings belong in NEITHER an email NOR a WhatsApp message, so stripping the
# marker — keeping the heading TEXT as a plain line — is safe for both kinds.
# Surgical on purpose: only the line-leading `#` run is removed, so a message's
# intentional inline WhatsApp emphasis (`*bold*`, `_italic_`) is untouched.
_DRAFT_HEADING_RE = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")


def _strip_draft_markdown(text: str) -> str:
    """Remove line-leading markdown heading markers from a draft body.

    Mechanics, not a semantic gate — the same "LLM decides, code ensures"
    discipline as `_extract_citations`: the prompt asks for plain prose, this
    guarantees it regardless of the model's unreliable adoption (lesson #74)."""
    return _DRAFT_HEADING_RE.sub("", text)


def extract_draft_core(normalized_text: str) -> str | None:
    """Return ONLY the fenced draft block plus its hoisted citation line,
    dropping any surrounding prose.

    Used by the presenter wrapper (Plan 3): the presenter supplies its OWN
    framing prose (pre_card / post_card), so the synthesis layer's own lead-in
    ("Here's an email draft reminding your students...:") that
    `normalize_rtf_draft` keeps BEFORE the fence must be dropped — otherwise the
    user sees two near-identical intros (the presenter pre_card + the synthesis
    lead-in). `normalize_rtf_draft` produces a deterministic layout
    (``` fence ``` then a single `[^N] [^N]` citation line), so we extract the
    fence and re-emit the de-duplicated citation markers that follow it.

    Returns None when there is no draft fence (caller keeps the original text).
    """
    if not normalized_text:
        return None
    m = _FENCED_BLOCK_RE.search(normalized_text)
    if m is None or m.group(1).strip().lower() not in _DRAFT_FENCE_LANGS:
        return None
    fence = normalized_text[m.start() : m.end()]
    # Citation markers anywhere after the fence (normalize hoists them to a
    # single line there). De-duplicated, order-preserving.
    nums: list[str] = []
    for n in _CITATION_RE.findall(normalized_text[m.end() :]):
        if n not in nums:
            nums.append(n)
    citation_line = _build_citation_line(nums)
    return f"{fence}\n\n{citation_line}" if citation_line else fence


def normalize_rtf_draft(text: str, draft_kind: str | None) -> str:
    """Guarantee a correctly-fenced, citation-clean draft for the `rtf` route.

    Args:
        text: the materialized answer the synthesis path produced for an
            `rtf`-routed request. Per the live probe (ROOT_CAUSE.md §2) this
            is the draft body itself — no "Here's a draft:" preamble.
        draft_kind: the supervisor's structured email/message decision
            (`"email"`, `"message"`, or `None`). Drives the fence tag.

    Returns:
        The answer with the draft body wrapped in exactly one
        ```email``` / ```message``` fence and all `[^N]` citation markers
        de-duplicated on a single line AFTER the closing fence.

    Deterministic and idempotent: a draft that already carries a valid
    draft fence keeps that fence (only its inner citations are hoisted), so
    calling this twice yields the same result.
    """
    if not text or not text.strip():
        return text

    fence_lang = _resolve_fence_lang(draft_kind)

    # --- Step 1: is there already a valid draft fence? ---
    existing = _FENCED_BLOCK_RE.search(text)
    if existing is not None and existing.group(1).strip().lower() in _DRAFT_FENCE_LANGS:
        lang = existing.group(1).strip().lower()
        body = existing.group(2)
        before = text[: existing.start()].rstrip()
        after = text[existing.end() :].lstrip()

        # --- Step 3 (on an already-fenced draft): hoist inner citations. ---
        body_clean, body_nums = _extract_citations(body)
        body_clean = _strip_draft_markdown(body_clean)
        # Citations may also already sit outside the fence (idempotent
        # re-run, or the model put some out and some in). Collect those too
        # and merge, de-duplicating across both sides.
        after_clean, after_nums = _extract_citations(after)
        before_clean, before_nums = _extract_citations(before)
        merged: list[str] = []
        for n in (*before_nums, *body_nums, *after_nums):
            if n not in merged:
                merged.append(n)

        rebuilt = f"```{lang}\n{body_clean.strip()}\n```"
        citation_line = _build_citation_line(merged)
        parts = [p for p in (before_clean.strip(), rebuilt) if p]
        result = "\n\n".join(parts)
        if citation_line:
            result = f"{result}\n\n{citation_line}"
        if after_clean.strip():
            result = f"{result}\n\n{after_clean.strip()}"
        return result

    # --- Step 2: no draft fence — wrap the body. ---
    # The body is the answer text minus any trailing "Sources:" /
    # citation-list block. We deliberately do NOT try to semantically
    # delineate the draft from surrounding prose (the PM rejected that as
    # its own fragility) — the live probe confirmed un-fenced `rtf` output
    # is draft-only, and the strengthened prompt keeps it that way.
    body, citation_nums = _extract_citations(text)
    body = body.strip()

    # If the model wrapped the draft in a NON-draft fence (e.g. ```text or a
    # bare ```), unwrap that single block and re-fence with the correct tag,
    # rather than nesting fences.
    plain_fence = _FENCED_BLOCK_RE.fullmatch(body)
    if plain_fence is not None:
        body = plain_fence.group(2).strip()

    body = _strip_draft_markdown(body)

    fenced = f"```{fence_lang}\n{body}\n```"
    citation_line = _build_citation_line(citation_nums)
    if citation_line:
        return f"{fenced}\n\n{citation_line}"
    return fenced


def hoist_draft_citations(text: str) -> str:
    """Move `[^N]` markers out of every ```email / ```message block.

    For the classic path, which has no draft route flag: the answer is never
    re-fenced or rewrapped, and prose outside the fences keeps its citations
    where they are. Only markers inside a draft fence move, de-duplicated, to
    a single line right after that fence. Idempotent; text without a draft
    fence is returned unchanged.

    Fences come from app.utils.links.split_fences, the same parser the sign-in
    annotator and citation coverage use, so all three agree on what is inside
    a draft. (The other functions in this module are upstream's supervisor
    path and aren't used by the classic path.)
    """
    if not text or "```" not in text:
        return text

    from app.utils.links import fence_info, split_fences

    out: list[str] = []
    for in_fence, segment in split_fences(text):
        if not in_fence:
            out.append(segment)
            continue
        lines = segment.splitlines(keepends=True)
        if fence_info(lines[0]) not in _DRAFT_FENCE_LANGS:
            out.append(segment)
            continue
        opening, body, closing = lines[0], "".join(lines[1:-1]), lines[-1]
        body_clean, nums = _extract_citations(body)
        if not nums:
            out.append(segment)
            continue
        # "[Student Name] [^2], hi" -> "[Student Name], hi", not "[Student Name] , hi".
        body_clean = re.sub(r"[ \t]+([,.;:!?])", r"\1", body_clean)
        ending = closing[len(closing.rstrip("\r\n")):]
        rebuilt = opening + body_clean.strip("\n") + "\n" + closing.rstrip("\r\n")
        out.append(f"{rebuilt}\n\n{_build_citation_line(nums)}{ending}")
    return "".join(out)
