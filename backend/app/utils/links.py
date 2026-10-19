"""One definition of "a link" and "a fenced block" in answer markdown.

Shared by link integrity (engine/grounding_guard.py), the sign-in annotator
(engine/login_links.py), and scripts/ask.py, so they can't disagree about
which URLs an answer contains or what is inside a drafted message. Pure
standard library: importing it pulls in nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A bare URL stops at whitespace, ')', brackets, angle brackets, '"', '*' and
# backticks, so "…A.aspx[^1]" ends before the citation marker and
# "**https://…**" / "`https://…`" don't drag their markdown into the URL.
URL_RE = re.compile(r"https?://[^\s)\[\]<>\"*`]+")
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


def is_fence_line(line: str) -> bool:
    """A line that opens or closes a fenced block (``` at the start)."""
    return line.lstrip().startswith("```")


def split_fences(text: str) -> list[tuple[bool, str]]:
    """Split `text` into (in_fence, segment) runs, line by line. Fence lines
    belong to the fenced run. An unclosed fence runs to the end. Joining the
    segments gives back `text` exactly."""
    runs: list[tuple[bool, str]] = []
    in_fence = False
    current: list[str] = []
    current_flag = False
    for line in text.splitlines(keepends=True):
        fence = is_fence_line(line)
        flag = True if fence else in_fence
        if current and flag != current_flag:
            runs.append((current_flag, "".join(current)))
            current = []
        current_flag = flag
        current.append(line)
        if fence:
            in_fence = not in_fence
    if current:
        runs.append((current_flag, "".join(current)))
    return runs
