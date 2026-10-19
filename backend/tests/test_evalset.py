"""The eval set file and the retrieval-eval scoring (CLAUDE.md §7 Phase 2). Offline."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evalset  # noqa: E402
from evalset import (  # noqa: E402
    EvalSetError,
    Question,
    contains_phrase,
    document_rank,
    hit_rank,
    load_eval_set,
    normal_url,
)


def _load_eval_retrieval():
    spec = importlib.util.spec_from_file_location("eval_retrieval", SCRIPTS / "eval_retrieval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path, text: str) -> Path:
    path = tmp_path / "questions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# --- the real file ---------------------------------------------------------------


def test_real_eval_set_loads_with_the_section_10_shape():
    eval_set = load_eval_set()
    ids = [q.id for q in eval_set.questions]

    assert ids == [str(i) for i in range(1, 22)] + ["G1", "G2", "G3", "G4"]
    assert [q.id for q in eval_set.retrieval_questions()] == [str(i) for i in range(1, 22)]
    assert {"missionar*", "My Gatherings", "ACM"} <= set(eval_set.default_must_not)
    assert "gathering" not in eval_set.default_must_not  # too common in ordinary advice


def test_real_eval_set_slugs_are_well_formed():
    for q in load_eval_set().questions:
        for slug in q.expect:
            assert slug == slug.lower() and slug.endswith("-ia"), (q.id, slug)
        for url in q.expect_url:
            assert url.startswith("https://"), (q.id, url)


def test_g4_mirrors_question_5_with_a_client_role():
    by_id = {q.id: q for q in load_eval_set().questions}
    g4 = by_id["G4"]
    assert g4.same_as == "5" and g4.q == by_id["5"].q
    assert g4.data == {"role": "missionary"}


# --- malformed files -----------------------------------------------------------------


@pytest.mark.parametrize(
    "body,message",
    [
        ("questions: []", "non-empty"),
        ("questions:\n  - {q: hi, kind: answer, expect: [a-ia]}", "needs an id"),
        ("questions:\n  - {id: '1', kind: answer, expect: [a-ia]}", "needs q"),
        ("questions:\n  - {id: '1', q: hi, kind: nope, expect: [a-ia]}", "kind must be"),
        ("questions:\n  - {id: '1', q: hi, kind: answer}", "expect"),
        ("questions:\n  - {id: '1', q: hi, kind: answer, expect: [a-ia]}\n"
         "  - {id: '1', q: ho, kind: answer, expect: [b-ia]}", "duplicate"),
        ("questions:\n  - {id: G4, q: hi, kind: guard, same_as: '9'}", "same_as"),
        ("questions:\n  - {id: '1', q: hi, kind: answer, expect: [a-ia], must_include: [[]]}", "empty group"),
    ],
)
def test_malformed_files_name_the_problem(tmp_path, body, message):
    with pytest.raises(EvalSetError, match=message):
        load_eval_set(_write(tmp_path, body))


def test_slugs_are_lowercased_and_strings_promoted_to_lists(tmp_path):
    path = _write(tmp_path, "questions:\n  - {id: '1', q: hi, kind: answer, expect: Academic-Integrity-IA}")
    assert load_eval_set(path).questions[0].expect == ("academic-integrity-ia",)


# --- matching ------------------------------------------------------------------------


def test_normal_url_ignores_fragment_trailing_slash_and_host_case():
    assert normal_url("HTTPS://WWW.BYUI.edu/genai/#top") == normal_url("https://www.byui.edu/genai")


def test_hit_rank_by_slug_and_by_url():
    by_slug = Question(id="1", q="q", kind="answer", expect=("b-ia",))
    by_url = Question(id="21", q="q", kind="linked", expect_url=("https://www.byui.edu/genai/",))
    ranked = [
        {"slug": "a-ia", "url": "https://x/a"},
        {"slug": "linked--www-byui-edu--genai", "url": "https://www.byui.edu/genai"},
        {"slug": "B-IA", "url": "https://x/b"},
    ]
    assert hit_rank(by_slug, ranked) == 3
    assert hit_rank(by_url, ranked) == 2
    assert hit_rank(by_slug, ranked[:2]) is None


def test_document_rank_counts_each_document_once():
    q = Question(id="1", q="q", kind="answer", expect=("c-ia",))
    ranked = [{"slug": "a-ia"}, {"slug": "a-ia"}, {"slug": "b-ia"}, {"slug": "a-ia"}, {"slug": "c-ia"}]
    assert hit_rank(q, ranked) == 5
    assert document_rank(q, ranked) == 3


# --- scoring ---------------------------------------------------------------------------


def _retrieval(raw, reranked, dropped=0):
    return {
        "raw": [(0.5, m) for m in raw],
        "reranked": [(0.9, m) for m in reranked],
        "dropped": dropped,
        "rerank_attempted": True,
        "rerank_ok": True,
        "rerank_error": None,
    }


def _meta(slug, role="instructor", source="instructor-assistant"):
    return {"slug": slug, "role": role, "source": source, "url": f"https://x/{slug}"}


def test_score_hit_miss_and_rerank_blame():
    er = _load_eval_retrieval()
    q = Question(id="1", q="q", kind="answer", expect=("want-ia",))
    filler = [_meta(f"other{i}-ia") for i in range(5)]

    hit = er.score_question(q, _retrieval([_meta("want-ia")], [_meta("want-ia")] + filler))
    assert hit["hit"] and hit["rank_after_rerank"] == 1

    lost = er.score_question(q, _retrieval(filler + [_meta("want-ia")], filler + [_meta("want-ia")]))
    assert not lost["hit"] and lost["rank_after_rerank"] == 6 and lost["rank_before_rerank"] == 6

    summary = er.summarize([hit, lost])
    assert summary["hit_at_5"] == 0.5 and not summary["passed"]
    assert summary["miss_causes"] == {"not_lifted": ["1"]}  # raw rank 6: rerank didn't lift it


def test_empty_context_and_non_instructor_nodes_fail_the_run():
    er = _load_eval_retrieval()
    q = Question(id="1", q="q", kind="answer", expect=("want-ia",))
    good = er.score_question(q, _retrieval([_meta("want-ia")], [_meta("want-ia")]))
    empty = er.score_question(q, _retrieval([_meta("want-ia")], []))
    leak = er.score_question(
        q, _retrieval([_meta("want-ia"), _meta("my-gatherings", role="missionary")], [_meta("want-ia")], dropped=1)
    )

    assert er.summarize([good])["passed"]
    assert empty["empty_context"] and not er.summarize([good, empty])["passed"]
    assert leak["non_instructor_nodes"] == ["my-gatherings"]
    leak_summary = er.summarize([good] * 9 + [leak])
    assert leak_summary["non_instructor_nodes"] == 1  # counted once, not again via guard_dropped
    assert not leak_summary["passed"]


def test_hit_target_is_ninety_percent():
    er = _load_eval_retrieval()
    q = Question(id="1", q="q", kind="answer", expect=("want-ia",))
    hit = er.score_question(q, _retrieval([_meta("want-ia")], [_meta("want-ia")]))
    miss = er.score_question(q, _retrieval([_meta("x-ia")], [_meta("x-ia")]))
    assert er.summarize([hit] * 9 + [miss])["passed"]  # 90%
    assert not er.summarize([hit] * 8 + [miss] * 2)["passed"]  # 80%


def test_eval_module_uses_the_indexer_top_k():
    assert evalset.TOP_K == 5


# --- review fixes ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,phrase,expected",
    [
        ("Macmillan publishes the textbook", "ACM", False),
        ("ask the ACM", "ACM", True),
        ("the guide says to provide it", "ID", False),
        ("include the student ID", "ID", True),
        ("AI readiness", "I read", False),
        ("I read the SharePoint page", "I read", True),
        ("start by gathering the facts", "gathering agenda*", False),
        ("the gathering agendas", "gathering agenda*", True),
        ("missionaries can help", "missionar*", True),
        ("due Saturday of Week 07", "Week 07", True),
        ("a sign-in page", "sign-in", True),
    ],
)
def test_phrases_match_whole_words(text, phrase, expected):
    assert contains_phrase(text, phrase) is expected


def _with_rank(er, before, after, attempted=True, ok=True):
    q = Question(id="x", q="q", kind="answer", expect=("want-ia",))
    filler = [_meta(f"o{i}-ia") for i in range(40)]

    def place(rank):
        if rank is None:
            return filler[:35]
        return filler[: rank - 1] + [_meta("want-ia")] + filler[rank - 1 : 34]

    retrieval = _retrieval(place(before), place(after)[:17])
    retrieval["rerank_attempted"], retrieval["rerank_ok"] = attempted, ok
    return er.score_question(q, retrieval)


@pytest.mark.parametrize(
    "before,after,attempted,ok,cause",
    [
        (2, 9, True, True, "lost_in_rerank"),
        (22, 8, True, True, "not_lifted"),  # rerank moved it UP; not rerank's fault
        (None, None, True, True, "not_retrieved"),
        (2, 9, True, False, "rerank_failed"),
    ],
)
def test_miss_causes_are_attributed_correctly(before, after, attempted, ok, cause):
    er = _load_eval_retrieval()
    row = _with_rank(er, before, after, attempted, ok)
    assert not row["hit"]
    assert er.summarize([row])["miss_causes"] == {cause: ["x"]}


def test_a_failed_rerank_fails_the_run_even_with_perfect_hits():
    er = _load_eval_retrieval()
    rows = [_with_rank(er, 1, 1, attempted=True, ok=False) for _ in range(10)]
    summary = er.summarize(rows)
    assert summary["hit_at_5"] == 1.0
    assert summary["rerank_failures"] == 10 and not summary["passed"]


def test_an_erroring_question_is_recorded_and_fails_the_run():
    er = _load_eval_retrieval()
    q = Question(id="18", q="q", kind="answer", expect=("want-ia",))
    good = _with_rank(er, 1, 1)
    bad = er.error_row(q, TimeoutError("Pinecone read timed out"))
    summary = er.summarize([good] * 20 + [bad])
    assert bad["error"].startswith("TimeoutError") and not bad["hit"]
    assert summary["errors"] == 1 and summary["miss_causes"] == {"error": ["18"]}
    assert not summary["passed"]  # 20/21 hits would otherwise pass


def test_non_instructor_check_uses_the_guards_rule(monkeypatch):
    er = _load_eval_retrieval()
    q = Question(id="1", q="q", kind="answer", expect=("want-ia",))
    monkeypatch.setenv("RETRIEVAL_SOURCES", "instructor-assistant")
    row = er.score_question(q, _retrieval(
        [_meta("want-ia"), _meta("linked-page", source="instructor-assistant-linked")], [_meta("want-ia")]
    ))
    # With the linked source switched off, a linked node is out of bounds, as the guard says.
    assert row["non_instructor_nodes"] == ["linked-page"]
