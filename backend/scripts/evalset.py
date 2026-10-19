"""Load and score the eval set in tests/eval/questions.yaml (CLAUDE.md §10).

Shared by scripts/eval_retrieval.py (Phase 2) and scripts/eval_answers.py
(Phase 6). Pure functions, no network, so tests can cover them offline.

A retrieval hit follows instructor-indexer `verify`: the question hits when
any expected document (by slug, or by URL for linked pages) appears among the
top `TOP_K` chunks. Here those chunks come after the production rerank, not
raw similarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urldefrag, urlparse

import yaml

QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "questions.yaml"
TOP_K = 5
KINDS = ("answer", "signin", "draft", "linked", "guard")


class EvalSetError(ValueError):
    """The question file is malformed. The message names the question."""


@dataclass(frozen=True)
class Question:
    id: str
    q: str
    kind: str
    expect: tuple[str, ...] = ()
    expect_url: tuple[str, ...] = ()
    must_include: tuple[tuple[str, ...], ...] = ()
    must_not: tuple[str, ...] = ()
    data: dict = field(default_factory=dict)
    same_as: str | None = None
    note: str = ""

    @property
    def scored_for_retrieval(self) -> bool:
        """Guards are checked on the answer (Phase 6), not on retrieval rank."""
        return self.kind != "guard" and bool(self.expect or self.expect_url)


@dataclass(frozen=True)
class EvalSet:
    questions: tuple[Question, ...]
    default_must_not: tuple[str, ...] = ()

    def retrieval_questions(self) -> list[Question]:
        return [q for q in self.questions if q.scored_for_retrieval]


def normal_url(url: str) -> str:
    """Compare addresses without a fragment, a trailing slash, or case in the
    scheme and host (same rule as instructor-indexer `verify`)."""
    bare = urldefrag(url.strip())[0]
    parts = urlparse(bare)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}" + (
        f"?{parts.query}" if parts.query else ""
    )


def _strings(value: Any, where: str, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise EvalSetError(f"{where}: {key} must be a string or a list of non-empty strings")
    return tuple(v.strip() for v in value)


def _groups(value: Any, where: str) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvalSetError(f"{where}: must_include must be a list of phrase groups")
    groups = []
    for group in value:
        phrases = _strings(group, where, "must_include group")
        if not phrases:
            raise EvalSetError(f"{where}: must_include has an empty group")
        groups.append(phrases)
    return tuple(groups)


def _question(item: Any, index: int) -> Question:
    if not isinstance(item, dict):
        raise EvalSetError(f"question #{index + 1} is not a mapping")
    qid = str(item.get("id") or "").strip()
    where = f"question {qid or f'#{index + 1}'}"
    if not qid:
        raise EvalSetError(f"{where}: needs an id")
    text = item.get("q")
    if not isinstance(text, str) or not text.strip():
        raise EvalSetError(f"{where}: needs q: (the question)")
    kind = item.get("kind")
    if kind not in KINDS:
        raise EvalSetError(f"{where}: kind must be one of {', '.join(KINDS)}")
    expect = tuple(s.lower() for s in _strings(item.get("expect"), where, "expect"))
    expect_url = _strings(item.get("expect_url"), where, "expect_url")
    if kind != "guard" and not (expect or expect_url):
        raise EvalSetError(f"{where}: needs expect: or expect_url:")
    data = item.get("data") or {}
    if not isinstance(data, dict):
        raise EvalSetError(f"{where}: data must be a mapping")
    same_as = item.get("same_as")
    return Question(
        id=qid,
        q=text.strip(),
        kind=kind,
        expect=expect,
        expect_url=expect_url,
        must_include=_groups(item.get("must_include"), where),
        must_not=_strings(item.get("must_not"), where, "must_not"),
        data=data,
        same_as=str(same_as) if same_as is not None else None,
        note=str(item.get("note") or ""),
    )


def load_eval_set(path: Path = QUESTIONS_PATH) -> EvalSet:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise EvalSetError(f"can't read {path}: {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("questions"), list) or not raw["questions"]:
        raise EvalSetError(f'{path} needs a non-empty "questions:" list')
    questions = tuple(_question(item, i) for i, item in enumerate(raw["questions"]))
    ids = [q.id for q in questions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise EvalSetError(f"duplicate question ids: {', '.join(duplicates)}")
    for q in questions:
        if q.same_as is not None and q.same_as not in ids:
            raise EvalSetError(f"question {q.id}: same_as {q.same_as!r} is not a question id")
    defaults = raw.get("defaults") or {}
    return EvalSet(questions, _strings(defaults.get("must_not"), "defaults", "must_not"))


def hit_rank(question: Question, ranked_metadata: Sequence[dict]) -> int | None:
    """1-based position of the first chunk from an expected document, or None."""
    urls = {normal_url(u) for u in question.expect_url}
    for rank, meta in enumerate(ranked_metadata, start=1):
        slug = str(meta.get("slug") or "").lower()
        if slug in question.expect or (urls and normal_url(str(meta.get("url") or "")) in urls):
            return rank
    return None


def document_rank(question: Question, ranked_metadata: Sequence[dict]) -> int | None:
    """Like hit_rank, but counting documents (each slug once), not chunks."""
    first_chunk_by_slug: dict[str, dict] = {}
    for meta in ranked_metadata:
        first_chunk_by_slug.setdefault(str(meta.get("slug") or "").lower(), meta)
    return hit_rank(question, list(first_chunk_by_slug.values()))


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """A case-insensitive whole-word match for an eval phrase.

    "ACM" doesn't match "Macmillan", "ID" doesn't match "guide", and "I read"
    doesn't match "AI readiness". A trailing `*` makes it a prefix:
    "missionar*" matches "missionary" and "missionaries". Phrases may contain
    spaces and punctuation ("Week 07", "11:59", "sign-in").
    """
    body = phrase.strip()
    prefix = body.endswith("*")
    if prefix:
        body = body[:-1]
    tail = r"\w*" if prefix else ""
    return re.compile(rf"(?<!\w){re.escape(body)}{tail}(?!\w)", re.IGNORECASE)


def contains_phrase(text: str, phrase: str) -> bool:
    return phrase_pattern(phrase).search(text) is not None
