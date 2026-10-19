"""Sign-in link annotator (CLAUDE.md §8.3).

Many instructor guides link to pages that need a BYU-Pathway or BYU-Idaho
sign-in (SharePoint, OneDrive, the course directory, Companion, the portal).
The bot has not read those pages. This guarantees the label: after the
grounding guards, every link whose host matches LOGIN_LINK_HOSTS (suffix match
on a domain boundary, so `*.sharepoint.com` is covered) gets the sign-in note
in the answer's language, once.

The note is this module's job, not the model's: the prompt tells the model not
to write one, so the label is always the localized one. A link already
followed by a sign-in label (one of the localized labels, or a strict English
form such as "(requires a BYU login)"; e.g. from an old answer in chat history,
or a model that wrote one anyway) is counted but not labeled again. Only
spaces, citation markers, and bold markers may sit between the link and the
label. A parenthetical that merely mentions signing in ("(sign in to WhatsApp
Web first)", "(Canvas login help)") is not a label.

Links inside fenced blocks are left alone: a ```message / ```email draft is
send-ready text for students, and a label would end up in it. Links and fences
are parsed by app.utils.links, the same parser link integrity uses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Union
from urllib.parse import urlparse

from app.utils.links import Link, find_links, split_fences
from app.utils.localization import LocalizationManager, MessageType

DEFAULT_LOGIN_LINK_HOSTS = (
    "sharepoint.com",
    "companion.byupathway.edu",
    "pathwayadmin.byui.edu",
    "portal.byupathway.edu",
)

# A parenthesized note directly after a link: "(…)" or full-width "（…）".
# Citation markers and bold may sit in between: "[Guide](url)[^1] (sign-in required)".
_NOTE_RE = re.compile(
    r"^[ \t]*(?:\[\^\d+\][ \t]*)*(?:\*\*|__)?[ \t]*[(（]([^()（）\n]{1,60})[)）]"
)
# English labels the model or a guide may write instead of ours. Strict on
# purpose: the whole note must be a label, not a sentence that mentions login.
_EN_LABEL_RE = re.compile(
    r"^(?:(?:sign[\s-]?in|log[\s-]?in|login)(?: is)? (?:required|needed)"
    r"|requires? (?:a |an )?(?:[\w-]+ ){0,2}(?:sign[\s-]?in|log[\s-]?in|login))$",
    re.IGNORECASE,
)

# A language code, or a function that works one out. The annotator calls it
# only when a link needs a label, so answers without one never pay for it.
Language = Union[str, None, Callable[[], str]]

@dataclass
class AnnotationResult:
    text: str
    links: int  # sign-in links outside fenced blocks (trace metadata `login_links`)
    added: int  # labels this call added


def login_link_hosts() -> list[str]:
    raw = os.getenv("LOGIN_LINK_HOSTS", "")
    hosts = [h.strip().lower().lstrip(".") for h in raw.split(",") if h.strip()]
    return hosts or list(DEFAULT_LOGIN_LINK_HOSTS)


def needs_sign_in(url: str, hosts: list[str] | None = None) -> bool:
    """True when the URL's host is a login host or a subdomain of one."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in (hosts or login_link_hosts()))


def sign_in_label(lang: str | None) -> str:
    return LocalizationManager.get_message(MessageType.SIGN_IN_REQUIRED, lang or "en")


def _normalize_note(note: str) -> str:
    return " ".join(note.strip().rstrip(".!").split()).lower()


@lru_cache(maxsize=1)
def _localized_labels() -> frozenset[str]:
    """Every localized label's text, without its parentheses, normalized."""
    labels = LocalizationManager.FALLBACK_MESSAGES[MessageType.SIGN_IN_REQUIRED].values()
    return frozenset(_normalize_note(label.strip("()（）")) for label in labels)


def has_sign_in_note(following: str) -> bool:
    """True when `following` (the text right after a link) opens with a
    parenthesized note that IS a sign-in label."""
    m = _NOTE_RE.match(following)
    if not m:
        return False
    note = _normalize_note(m.group(1))
    return note in _localized_labels() or bool(_EN_LABEL_RE.match(note))


def _label_point(segment: str, link: Link) -> int:
    """Where a label for `link` goes: right after it, or after the closing
    parenthesis when a bare URL is wrapped in parentheses ("(https://…)"), so
    the label doesn't land inside them."""
    if (
        link.kind == "bare"
        and link.start > 0
        and segment[link.start - 1] == "("
        and segment[link.end:link.end + 1] == ")"
    ):
        return link.end + 1
    return link.end


def unlabeled_login_links(text: str, hosts: list[str] | None = None) -> list[str]:
    """URLs of sign-in links outside fenced blocks that have no note. Used by
    the annotator and by scripts/ask.py's check, so both apply one rule."""
    hosts = hosts or login_link_hosts()
    missing: list[str] = []
    for in_fence, segment in split_fences(text):
        if in_fence:
            continue
        for link in find_links(segment):
            if needs_sign_in(link.url, hosts) and not has_sign_in_note(segment[_label_point(segment, link):]):
                missing.append(link.url)
    return missing


def annotate_login_links(text: str, lang: Language = "en") -> AnnotationResult:
    """Append the localized sign-in note after every unlabeled sign-in link.

    `lang` is a language code, or a function returning one, called only if a
    label is needed. Idempotent: a second run finds the note and adds nothing.
    Fenced blocks are copied through untouched.
    """
    if not text or "http" not in text:
        return AnnotationResult(text, 0, 0)
    hosts = login_link_hosts()
    resolved: list[str] = []

    def label() -> str:
        if not resolved:
            resolved.append(sign_in_label(lang() if callable(lang) else lang))
        return resolved[0]

    out: list[str] = []
    links = added = 0
    for in_fence, segment in split_fences(text):
        if in_fence:
            out.append(segment)
            continue
        cursor = 0
        for link in find_links(segment):
            if not needs_sign_in(link.url, hosts):
                continue
            links += 1
            point = _label_point(segment, link)
            out.append(segment[cursor:point])
            cursor = point
            if not has_sign_in_note(segment[point:]):
                out.append(f" {label()}")
                added += 1
        out.append(segment[cursor:])
    return AnnotationResult("".join(out), links, added)
