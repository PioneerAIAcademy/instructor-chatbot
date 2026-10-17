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
    """Attach a top-source marker to uncited substantive lines.

    Last-resort presentation guard after synthesis. It does not replace real
    citation placement (the prompts own that) — it just prevents a cited
    answer from displaying claim-bearing bullets or paragraphs with no visible
    evidence trail.

    Two cases are left alone:
    - An answer with no citations at all. That is a refusal or an
      ungrounded reply, and stamping [^1] on it would fake a source.
    - Fenced code blocks, including the fence lines. A ```message/```email
      draft must stay send-ready text, and a marker on the opening fence
      would break the frontend's DraftComposer.
    """
    if not text or not source_nodes or not _CITATION_RE.search(text):
        return text

    marker = "[^1]"
    fixed_lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            fixed_lines.append(line)
            continue
        if in_fence or not _line_needs_citation(stripped):
            fixed_lines.append(line)
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            fixed_lines.append(_append_marker_to_table_row(line, marker))
        else:
            fixed_lines.append(line.rstrip() + f" {marker}")
    return "\n".join(fixed_lines)


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


_URL_RE = re.compile(r"https?://[^\s)\]]+")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


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
    return u.rstrip("/.,);")


def _allowed_urls(source_nodes: list[Any]) -> set[str]:
    """Every URL the answer may surface: each node's metadata url + any http(s)
    URL appearing in node text."""
    allowed: set[str] = set()
    for n in source_nodes or []:
        url, text = _node_url_and_text(n)
        if url:
            allowed.add(_norm_url(url))
        for m in _URL_RE.findall(text):
            allowed.add(_norm_url(m))
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
    kept: list[str] = []

    def _md_sub(m: "re.Match[str]") -> str:
        label, url = m.group(1), m.group(2)
        if _norm_url(url) in allowed:
            token = f"\x00KEPT{len(kept)}\x00"
            kept.append(m.group(0))
            return token  # protect kept md-links from the bare-URL pass
        return label

    out = _MD_LINK_RE.sub(_md_sub, text)

    def _bare_sub(m: "re.Match[str]") -> str:
        return m.group(0) if _norm_url(m.group(0)) in allowed else ""

    out = _URL_RE.sub(_bare_sub, out)
    for i, original in enumerate(kept):
        out = out.replace(f"\x00KEPT{i}\x00", original)
    return re.sub(r"[ \t]{2,}", " ", out)


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
    The deterministic steps are presentation-only: make citations visible,
    de-clutter runs of the same repeated citation, then strip any link/URL the
    answer surfaced that is NOT present in the retrieved sources (anti-fabrication).
    """
    text = decluster_citations(ensure_citation_coverage(text, source_nodes))
    return enforce_link_integrity(text, source_nodes)
