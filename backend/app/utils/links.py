"""One definition of "a link" and "a fenced block" in answer markdown.

Shared by link integrity (engine/grounding_guard.py), the sign-in annotator
(engine/login_links.py), and scripts/ask.py, so they can't disagree about
which URLs an answer contains or what is inside a drafted message. Pure
standard library: importing it pulls in nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A bare URL stops at whitespace, ')', brackets, angle brackets, '"', '*',
# backticks, and any non-ASCII character, so "…A.aspx[^1]" ends before the
# citation marker, "**https://…**" / "`https://…`" don't drag their markdown in,
# and CJK punctuation ("…/x。", "…/x）") isn't read as part of the URL. The
# guides' URLs are ASCII (non-ASCII is percent-encoded).
URL_RE = re.compile(r"https?://[^\s)\[\]<>\"*`\u0080-\U0010ffff]+")
# [label](url) or [label](url "title").
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)\"]+)(\s+\"[^\"]*\")?\)")
# <https://…> autolinks.
AUTOLINK_RE = re.compile(r"<(https?://[^\s>]+)>")
# Sentence punctuation and emphasis markers that end a bare URL ("__url__", "~~url~~").
TRAILING_PUNCT = ".,;:!?'_~"


@dataclass(frozen=True)
class Link:
    start: int  # where the link's markdown starts
    end: int  # just past the link's markdown: after ')' or '>', or the bare URL
    url: str
    kind: str  # "markdown" | "autolink" | "bare"
    label: str = ""  # a markdown link's text


def find_links(text: str) -> list[Link]:
    """Every link in `text`, in order, never overlapping: markdown links,
    autolinks outside them, then bare URLs outside both. Trailing sentence
    punctuation and emphasis markers are not part of a bare URL."""
    links: list[Link] = [
        Link(m.start(), m.end(), m.group(2), "markdown", m.group(1)) for m in MD_LINK_RE.finditer(text)
    ]

    def inside(pos: int) -> bool:
        return any(link.start <= pos < link.end for link in links)

    # A link nested inside another (an autolink in a markdown link's label, a
    # bare URL inside either) belongs to the outer one, so spans never overlap.
    for m in AUTOLINK_RE.finditer(text):
        if not inside(m.start()):
            links.append(Link(m.start(), m.end(), m.group(1), "autolink"))
    for m in URL_RE.finditer(text):
        if inside(m.start()):
            continue
        url = m.group(0).rstrip(TRAILING_PUNCT)
        if url:
            links.append(Link(m.start(), m.start() + len(url), url, "bare"))
    return sorted(links, key=lambda link: link.start)


# CommonMark-style fences: an opening line is ``` plus an optional info string
# (no backticks in it), a closing line is ``` alone. Up to 3 spaces of indent.
# "```Week 07``` is the last week" is an inline code span, not a fence.
_OPEN_FENCE_RE = re.compile(r"^ {0,3}```([^`\n]*)$")
_CLOSE_FENCE_RE = re.compile(r"^ {0,3}```[ \t]*$")


def fence_info(line: str) -> str | None:
    """The info string ("message", "email", "") if `line` opens a fence, else None."""
    m = _OPEN_FENCE_RE.match(line.rstrip("\r\n"))
    return m.group(1).strip().lower() if m else None


def split_fences(text: str) -> list[tuple[bool, str]]:
    """Split `text` into (in_fence, segment) runs, line by line. A fenced run
    includes its opening and closing lines. An opening line with no closing
    line after it is NOT a fence: everything stays ordinary text, so a
    forgotten closing line can't switch off sign-in labels or citation
    coverage for the rest of the answer. Joining the segments gives back
    `text` exactly."""
    lines = text.splitlines(keepends=True)
    runs: list[tuple[bool, str]] = []
    plain: list[str] = []
    i = 0
    while i < len(lines):
        if fence_info(lines[i]) is not None:
            close = next(
                (j for j in range(i + 1, len(lines)) if _CLOSE_FENCE_RE.match(lines[j].rstrip("\r\n"))),
                None,
            )
            if close is not None:
                if plain:
                    runs.append((False, "".join(plain)))
                    plain = []
                runs.append((True, "".join(lines[i:close + 1])))
                i = close + 1
                continue
        plain.append(lines[i])
        i += 1
    if plain:
        runs.append((False, "".join(plain)))
    return runs
