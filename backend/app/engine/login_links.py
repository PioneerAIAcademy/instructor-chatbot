"""Sign-in link annotator (CLAUDE.md §8.3).

Many instructor guides link to pages that need a BYU-Pathway or BYU-Idaho
sign-in (SharePoint, OneDrive, the course directory, Companion, the portal).
The bot has not read those pages. This guarantees the label: after the
grounding guards, every link whose host matches LOGIN_LINK_HOSTS (suffix match
on a domain boundary, so `*.sharepoint.com` is covered) gets the sign-in note
in the answer's language, once.

The note is this module's job, not the model's: the prompt tells the model not
to write one, so the label is always the localized one. A link already
followed by a parenthesized sign-in note (in any supported language, e.g. from
an old answer in chat history or a model that wrote one anyway) is counted but
not labeled again. A sentence that merely mentions signing in ("then sign in to
WhatsApp Web") is not a label.

Links inside fenced blocks are left alone: a ```message / ```email draft is
send-ready text for students, and a label would end up in it. Links and fences
are parsed by app.utils.links, the same parser link integrity uses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.utils.links import find_links, split_fences
from app.utils.localization import LocalizationManager, MessageType

DEFAULT_LOGIN_LINK_HOSTS = (
    "sharepoint.com",
    "companion.byupathway.edu",
    "pathwayadmin.byui.edu",
    "portal.byupathway.edu",
)

# A parenthesized note right after a link: "(…)" or full-width "（…）", within
# this many characters of the link (§8.3's 40-character lookahead).
LOOKAHEAD_CHARS = 40
_NOTE_RE = re.compile(r"^[ \t]*(?:\*\*|__)?[ \t]*[(（]([^()（）\n]{1,60})[)）]")

# English wordings the model or a guide may use inside such a note.
_EN_NOTE_WORDS = ("sign-in", "sign in", "signin", "log-in", "log in", "login")


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


def _note_words() -> tuple[str, ...]:
    """Every localized label's words, plus English variants, lowercased."""
    labels = LocalizationManager.FALLBACK_MESSAGES[MessageType.SIGN_IN_REQUIRED].values()
    words = {label.strip("()（） ").lower() for label in labels}
    return tuple(words) + _EN_NOTE_WORDS


def has_sign_in_note(following: str) -> bool:
    """True when `following` (the text right after a link) opens with a
    parenthesized sign-in note."""
    m = _NOTE_RE.match(following[:LOOKAHEAD_CHARS + 20])
    if not m or m.start(1) > LOOKAHEAD_CHARS:
        return False
    note = m.group(1).lower()
    return any(word in note for word in _note_words())


def unlabeled_login_links(text: str, hosts: list[str] | None = None) -> list[str]:
    """URLs of sign-in links outside fenced blocks that have no note. Used by
    the annotator and by scripts/ask.py's check, so both apply one rule."""
    hosts = hosts or login_link_hosts()
    missing: list[str] = []
    for in_fence, segment in split_fences(text):
        if in_fence:
            continue
        for link in find_links(segment):
            if needs_sign_in(link.url, hosts) and not has_sign_in_note(segment[link.end:]):
                missing.append(link.url)
    return missing


def annotate_login_links(text: str, lang: str | None = "en") -> AnnotationResult:
    """Append the localized sign-in note after every unlabeled sign-in link.

    Idempotent: a second run finds the note and adds nothing. Fenced blocks
    are copied through untouched.
    """
    if not text or "http" not in text:
        return AnnotationResult(text, 0, 0)
    label = sign_in_label(lang)
    hosts = login_link_hosts()

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
            out.append(segment[cursor:link.end])
            cursor = link.end
            if not has_sign_in_note(segment[link.end:]):
                out.append(f" {label}")
                added += 1
        out.append(segment[cursor:])
    return AnnotationResult("".join(out), links, added)
