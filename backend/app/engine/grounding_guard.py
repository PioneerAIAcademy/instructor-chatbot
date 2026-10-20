"""Presentation-only safety net for sourced RAG answers.

This module deliberately holds NO topic-specific answer text. Grounding is
the job of the agentic loop: retrieval digs the corpus, the synthesis/
sub-agent prompts demand source-grounded prose, and the hallucination +
form/link critics catch wrong substitutions and unsupported claims.

The main thing here is `ensure_citation_coverage` — a last-resort
PRESENTATION guard that attaches a visible citation marker to a
substantive line that the model left uncited. It never writes, removes,
or rephrases answer content; it only makes the evidence trail visible.

History: this file once carried deterministic per-topic answers for the
Auto-Drop Exemption form and EnglishConnect-drop policy. Those were
removed 2026-05-21 — hardcoded answer text goes stale the moment a source
doc changes, makes the bot "confident here, shy there", and bypasses the
agentic loop that should be doing the digging. Hardcoding is for security,
not for content.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.links import find_links, split_fences

_CITATION_RE = re.compile(r"\[\^\d+\]")


def _is_table_separator(stripped: str) -> bool:
    if not stripped:
        return False
    compact = stripped.replace("|", "").replace(":", "").replace("-", "").strip()
    return compact == ""


# Openers of lines that legitimately carry no citation: refusals, caveats about
# what the guides don't cover, and link leads. English only — a caveat in
# another language can still pick up a marker when the answer has other
# citations (a wholly uncited answer gets none; see ensure_citation_coverage).
_UNCITED_LINE_OPENERS = (
    "**link:**",
    "link:",
    "i couldn't find",
    "i could not find",
    "i can't find",
    "i don't have",
    "i do not have",
    "for more detailed information",
    "for more specific details",
    "the guides don't",
    "the guides do not",
    "the guide doesn't",
    "the guide does not",
    "the instructor guides don't",
    "the instructor guides do not",
    "the contexts don't",
    "the sources don't",
    "that's outside",
    "that is outside",
    "this is outside",
    "this isn't covered",
    "that isn't covered",
    "it isn't covered",
)


def _is_caveat_or_link_line(stripped: str) -> bool:
    """Lines that legitimately carry no citation: refusals, caveats, link leads."""
    return stripped.lower().replace("\u2019", "'").startswith(_UNCITED_LINE_OPENERS)


def _line_needs_citation(stripped: str) -> bool:
    if (
        not stripped
        or _CITATION_RE.search(stripped)
        or stripped.startswith("#")
        or _is_table_separator(stripped)
        or _is_caveat_or_link_line(stripped)
    ):
        return False
    return any(ch.isalpha() for ch in stripped)


def _append_marker_to_table_row(line: str, marker: str) -> str:
    cells = line.split("|")
    for idx in range(len(cells) - 1, -1, -1):
        if cells[idx].strip():
            cells[idx] = cells[idx].rstrip() + f" {marker}"
            break
    return "|".join(cells)


def ensure_citation_coverage(text: str, source_nodes: list[Any]) -> str:
    """Attach the nearest real citation to uncited substantive lines.

    Last-resort presentation guard after synthesis. It does not replace real
    citation placement (the prompts own that) — it just prevents a cited
    answer from displaying claim-bearing bullets or paragraphs with no visible
    evidence trail.

    Which marker: the last citation before the line, or (for lines before any
    citation) the first one after it. Upstream always stamped [^1], which
    pointed lines at whatever guide happened to be source 1: in the Phase 6
    eval, an intro and a summary line cited the due-date guide in an answer
    built from the adds/drops and pre-term guides.

    Left alone:
    - A lead-in line ending in ":" ("Here's what to do:"). It introduces a
      list and makes no claim of its own.
    - An answer with no citations at all. That is a refusal or an
      ungrounded reply, and stamping [^1] on it would fake a source.
    - Fenced code blocks, including the fence lines. A ```message/```email
      draft must stay send-ready text, and a marker on the opening fence
      would break the frontend's DraftComposer.
    """
    if not text or not source_nodes or not _CITATION_RE.search(text):
        return text

    # Fences come from app.utils.links, the same parser the sign-in annotator uses.
    segments = split_fences(text)
    prose = "".join(seg for in_fence, seg in segments if not in_fence)
    first_marker = next(iter(_CITATION_RE.findall(prose)), None)
    if first_marker is None:  # the only citations are inside a draft fence
        return text
    last_marker: str | None = None

    out: list[str] = []
    for in_fence, segment in segments:
        if in_fence:
            out.append(segment)
            continue
        for line in segment.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            stripped = body.strip()
            cited = _CITATION_RE.findall(body)
            if cited:
                last_marker = cited[-1]
            if not _line_needs_citation(stripped) or stripped.endswith(":"):
                out.append(line)
                continue
            marker = last_marker or first_marker  # a whole "[^N]"
            if stripped.startswith("|") and stripped.endswith("|"):
                out.append(_append_marker_to_table_row(body, marker) + ending)
            else:
                out.append(body.rstrip() + f" {marker}" + ending)
    return "".join(out)


def _has_citation_boundary(between: str) -> bool:
    """True when two citation markers are far enough apart that repeating
    the citation is OK: a paragraph break, a heading, or a long span. The
    citation may legitimately re-anchor across these."""
    return "\n\n" in between or "\n#" in between or len(between) > 600


def decluster_citations(text: str) -> str:
    """Drop redundant consecutive citations so the answer isn't littered
    with the same `[^N]` on line after line.

    Rule (per user directive 2026-05-22): a run of sentences or list items
    that all cite the SAME single source keeps the marker only on the LAST
    one of the run. When the source CHANGES the new marker appears; the old
    one may re-appear later. A paragraph break, heading, or long span
    re-anchors. Markers with different numbers are never touched, and an
    adjacent pair like `[^1][^2]` is left intact.
    """
    if not text:
        return text
    markers = list(_CITATION_RE.finditer(text))
    remove: list[tuple[int, int]] = []
    prev: tuple[str, int, int] | None = None  # (marker, start, end)
    for m in markers:
        marker = m.group(0)
        if (
            prev is not None
            and marker == prev[0]
            and m.start() > prev[2]  # not directly adjacent ([^1][^1])
            and not _has_citation_boundary(text[prev[2]:m.start()])
        ):
            # Redundant — keep the LAST of the run, drop the earlier one.
            remove.append((prev[1], prev[2]))
        prev = (marker, m.start(), m.end())
    for start, end in sorted(remove, reverse=True):
        # Swallow one leading space so "word [^1]." doesn't become "word  .".
        lead = 1 if start > 0 and text[start - 1] == " " else 0
        text = text[: start - lead] + text[end:]
    return text


def _node_url_and_text(node: Any) -> tuple[str | None, str]:
    """Extract (url, text) from any source-node shape: dict, NodeWithScore, or
    the supervisor's `_SourceNodeAdapter` (mirrors critic.py lesson #103/#66)."""
    if isinstance(node, dict):
        meta = node.get("metadata") or {}
        text = node.get("text") or ""
    else:
        meta = getattr(node, "metadata", None)
        if meta is None:
            inner = getattr(node, "node", None)
            meta = getattr(inner, "metadata", None) or {}
        text = getattr(node, "text", None)
        if not text:
            inner = getattr(node, "node", None)
            text = inner.get_text() if (inner is not None and hasattr(inner, "get_text")) else ""
    url = meta.get("url") if isinstance(meta, dict) else None
    if not isinstance(url, str):
        url = None
    if not isinstance(text, str):
        text = ""
    return url, text


def _norm_url(u: str) -> str:
    return u.rstrip("/.,);*_~`")


def _allowed_urls(source_nodes: list[Any]) -> set[str]:
    """Every URL the answer may surface: each node's metadata url + any http(s)
    URL appearing in node text."""
    allowed: set[str] = set()
    for n in source_nodes or []:
        url, text = _node_url_and_text(n)
        if url:
            allowed.add(_norm_url(url))
        for link in find_links(text):
            allowed.add(_norm_url(link.url))
    return allowed


def enforce_link_integrity(text: str, source_nodes: list[Any]) -> str:
    """Strip any markdown link or bare http(s) URL whose URL is NOT present in
    the retrieved sources (node metadata url or node text), keeping the link's
    label as plain text. Stops the bot from emitting a fabricated/dead link the
    frontend would render as a live (wrong) hyperlink. Citation markers,
    relative links and anchors are untouched. Deterministic, language-agnostic.
    """
    if not text:
        return text
    allowed = _allowed_urls(source_nodes)
    out: list[str] = []
    cursor = 0
    for link in find_links(text):  # app.utils.links: the same parser as the annotator
        out.append(text[cursor:link.start])
        cursor = link.end
        if _norm_url(link.url) in allowed:
            out.append(text[link.start:link.end])
        elif link.kind == "markdown":
            out.append(link.label)  # keep the words, drop the dead link
        # an unknown bare URL or autolink is dropped; trailing punctuation stays
        elif out and out[-1].endswith(" ") and text[cursor:cursor + 1] == " ":
            # The link sat between two spaces; drop one, so "see LINK now" reads
            # "see now". Whitespace elsewhere (list indents, drafts, hard line
            # breaks) is left exactly as written.
            out[-1] = out[-1][:-1]
    out.append(text[cursor:])
    return "".join(out)


# A citation the model wrote in a near-miss form: "[^1^]" (seen live in the
# Phase 6 eval), "[^ 1]", "[^1 ]". The frontend and the eval only recognize
# "[^1]", so a near miss would show as a stray token and count as uncited.
_MALFORMED_CITATION_RE = re.compile(r"\[\^[ \t]*(\d+)[ \t]*\^?[ \t]*\]")


# A marker with no number at all: the prompt's own placeholder "[^N]" copied
# literally (seen live in the Phase 6 eval, #6). It points at nothing.
_PLACEHOLDER_CITATION_RE = re.compile(r"[ \t]*\[\^[ \t]*[A-Za-z][ \t]*\]")


def normalize_citation_markers(text: str) -> str:
    """Rewrite near-miss citation markers to the canonical [^N], and drop
    numberless placeholders such as a literal "[^N]", which the reader would
    otherwise see as-is."""
    text = _MALFORMED_CITATION_RE.sub(r"[^\1]", text or "")
    return _PLACEHOLDER_CITATION_RE.sub("", text)


def apply_grounding_guards(
    text: str,
    source_nodes: list[Any],
    *,
    user_question: str = "",
    chat_history: list[Any] | None = None,
) -> str:
    """Thin passthrough kept for call-site compatibility.

    `user_question` / `chat_history` are accepted but unused — grounding
    judgement now lives entirely in the agentic loop (retrieval + critics).
    The deterministic steps are presentation-only: repair near-miss citation
    markers ("[^1^]" to "[^1]"), make citations visible,
    de-clutter runs of the same repeated citation, then strip any link/URL the
    answer surfaced that is NOT present in the retrieved sources (anti-fabrication).
    """
    text = normalize_citation_markers(text)
    text = decluster_citations(ensure_citation_coverage(text, source_nodes))
    return enforce_link_integrity(text, source_nodes)
