"""The answer eval's scoring (CLAUDE.md §7 Phase 6). Offline: answers are
built by hand, nothing is sent anywhere."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import requests

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evalset import load_eval_set  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("eval_answers", SCRIPTS / "eval_answers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = _load()
EVAL_SET = load_eval_set()
BY_ID = {q.id: q for q in EVAL_SET.questions}
PAY = "pay-dates-for-worldwide-online-instructors-ia"


def _source(n, slug, *, role="instructor", source="instructor-assistant", url=None, node_id=None):
    url = url or f"https://missionaries.prod.byu-pathway.psdops.com/{slug}"
    return {
        "id": node_id or f"{slug}#{n:04d}", "citation_node_id": str(n), "url": url, "text": "t", "score": 0.7,
        "metadata": {"slug": slug, "source": source, "role": role, "url": url, "title": slug, "sequence": n},
    }


def _result(answer, sources=(), **extra):
    return {"answer": answer, "sources": list(sources), "contract_problems": [], "trace_id": "t1", **extra}


def _score(qid, result, reference=None):
    q = ev.effective(BY_ID[qid], BY_ID)
    return ev.score_answer(q, result, default_must_not=EVAL_SET.default_must_not, reference=reference)


def _failed(scored):
    return {name for name, c in scored["checks"].items() if c["status"] == "failed"}


# --- the eval set --------------------------------------------------------------------


def test_refusal_questions_are_guards_without_expected_documents():
    refusing = [q for q in EVAL_SET.questions if q.refuse]
    assert {q.id for q in refusing} == {"G1", "G2"}
    assert all(q.kind == "guard" and not q.expect for q in refusing)


def test_g4_inherits_the_checks_of_question_5():
    g4 = ev.effective(BY_ID["G4"], BY_ID)
    assert g4.expect == BY_ID["5"].expect and g4.must_include == BY_ID["5"].must_include
    assert g4.data == {"role": "missionary"}


# --- one answer's checks -------------------------------------------------------------


def test_a_good_answer_passes():
    scored = _score("1", _result("You're paid on the 8th and the 23rd [^1].", [_source(1, PAY)]))
    assert scored["passed"], scored["checks"]
    assert scored["checks"]["refusal"]["status"] == "skipped"


def test_expected_document_must_be_cited_not_just_returned():
    other = _source(2, "academic-integrity-ia")
    scored = _score("1", _result("Paid on the 8th and 23rd [^2].", [_source(1, PAY), other]))
    assert _failed(scored) == {"cites_expected"}


def test_dangling_citation_fails():
    scored = _score("1", _result("Paid on the 8th and 23rd [^1][^4].", [_source(1, PAY)]))
    assert "citations_resolve" in _failed(scored)


def test_non_instructor_source_fails():
    bad = _source(2, "gathering-agenda", role="missionary", source="pathway")
    scored = _score("1", _result("Paid on the 8th and 23rd [^1].", [_source(1, PAY), bad]))
    assert "instructor_sources" in _failed(scored)


def test_must_include_groups_and_must_not_phrases():
    assert "must_include" in _failed(_score("1", _result("Paid on the 8th [^1].", [_source(1, PAY)])))
    scored = _score("1", _result("Like missionaries, you're paid on the 8th and 23rd [^1].", [_source(1, PAY)]))
    assert _failed(scored) == {"must_not"}


def test_a_phrase_the_question_contains_may_be_repeated():
    # G2 asks about "My Gatherings"; saying the guides don't cover it is right.
    scored = _score("G2", _result("The instructor guides don't cover My Gatherings."))
    assert scored["passed"], scored["checks"]


def test_unlabeled_sign_in_link_fails_and_labeled_passes():
    link = "[course directory](https://pathwayadmin.byui.edu/directory)"
    src = [_source(1, "how-do-i-find-my-acl-other-instructors-ia")]
    base = "Use the BYU-Idaho course directory to find your ACL: "
    assert "sign_in_labels" in _failed(_score("9", _result(f"{base}{link} [^1].", src)))
    assert _score("9", _result(f"{base}{link} (sign-in required) [^1].", src))["passed"]


@pytest.mark.parametrize("answer", [
    "I can only help with questions about teaching through BYU-Pathway.",
    "That isn't covered in the instructor guides.",
    "The instructor guides don’t have information about that.",
])
def test_refusals_pass(answer):
    assert _score("G1", _result(answer))["passed"]


def test_answering_from_general_knowledge_fails_the_refusal():
    scored = _score("G1", _result("The capital of Nigeria is Abuja."))
    assert {"refusal", "must_not"} <= _failed(scored)


def test_a_refusal_that_cites_a_source_fails():
    scored = _score("G1", _result("That isn't covered in the guides [^1].", [_source(1, PAY)]))
    assert "refusal" in _failed(scored)


def test_draft_needs_a_message_fence_without_citations():
    src = [_source(1, "send-a-welcome-message-to-students-ia")]
    good = "Here's a draft [^1]:\n\n```message\nHi [Student Name], welcome to [Course]!\n```\n"
    assert _score("17", _result(good, src))["passed"]
    inside = "Here's a draft:\n\n```message\nHi [Student Name] [^1]\n```\n"
    assert "draft" in _failed(_score("17", _result(inside, src)))
    no_fence = "Hi [Student Name], welcome [^1]."
    assert "draft" in _failed(_score("17", _result(no_fence, src)))


def test_linked_page_is_matched_by_url():
    src = [_source(1, "linked--www-byui-edu--genai", source="instructor-assistant-linked",
                   url="https://www.byui.edu/genai")]
    answer = "BYU-Idaho's external page on generative AI says to follow each course's policy [^1]."
    assert _score("21", _result(answer, src))["passed"]


def test_g4_needs_the_same_sources_as_question_5():
    ferpa = "ferpa-adjunct-faculty-responsibilities-ia"
    answer = "No. Under FERPA you need the student's written consent [^1]."
    reference = _result(answer, [_source(1, ferpa)])
    assert _score("G4", _result(answer, [_source(1, ferpa)]), reference=reference)["passed"]
    # An extra source ranked ABOVE the shared one is a real difference.
    higher = _source(2, PAY)
    higher["score"] = 0.9
    extra = _result(answer, [_source(1, ferpa), higher])
    assert _failed(_score("G4", extra, reference=reference)) == {"same_sources"}
    assert "same_sources" in _failed(_score("G4", _result(answer, [_source(1, ferpa)]), reference=None))


def test_an_error_or_a_broken_stream_fails():
    assert _failed(_score("1", {"error": "HTTP 500"})) == {"stream"}
    broken = _result("Paid on the 8th and 23rd [^1].", [_source(1, PAY)], contract_problems=["missing sources annotation"])
    assert _failed(_score("1", broken)) == {"stream"}
    assert "stream" in _failed(_score("1", _result("   ", [_source(1, PAY)])))


# --- the run ----------------------------------------------------------------------


def _row(qid, kind, passed):
    return {"id": qid, "kind": kind, "passed": passed, "error": None,
            "checks": {"x": {"status": "ok" if passed else "failed", "detail": ""}}}


def test_summary_targets():
    answers = [_row(str(i), "answer", i > 3) for i in range(1, 22)]  # 18/21 = 86%
    guards = [_row(f"G{i}", "guard", True) for i in range(1, 5)]
    assert ev.summarize(answers + guards)["passed"]
    assert not ev.summarize([_row(str(i), "answer", i > 4) for i in range(1, 22)] + guards)["passed"]  # 81%
    one_guard_failed = guards[:3] + [_row("G4", "guard", False)]
    summary = ev.summarize(answers + one_guard_failed)
    assert not summary["passed"] and summary["failed_checks"]["x"][-1] == "G4"


def test_rate_limit_is_waited_out_not_failed():
    calls, waits = [], []

    def _ask(q, url, data=None, session_id=None):
        calls.append(session_id)
        if len(calls) == 1:
            resp = requests.Response()
            resp.status_code = 429
            resp.headers["Retry-After"] = "7"
            raise requests.HTTPError(response=resp)
        return _result("ok")

    result = ev.ask_with_retry(_ask, BY_ID["1"], "http://x", "eval-r1", sleep=waits.append)
    assert result["answer"] == "ok" and waits == [7.0] and calls == ["eval-r1", "eval-r1"]


def test_other_failures_become_an_error_result():
    def _ask(*a, **k):
        raise requests.ConnectionError("refused")

    assert ev.ask_with_retry(_ask, BY_ID["1"], "http://x", "eval-r1")["error"].startswith("ConnectionError")


def test_guard_data_is_sent():
    seen = {}

    def _ask(q, url, data=None, session_id=None):
        seen["data"] = data
        return _result("ok")

    ev.ask_with_retry(_ask, ev.effective(BY_ID["G4"], BY_ID), "http://x", "eval-r1")
    assert seen["data"] == {"role": "missionary"}


def test_evalset_rejects_a_non_boolean_refuse(tmp_path):
    from evalset import EvalSetError

    path = tmp_path / "q.yaml"
    path.write_text('questions:\n  - {id: G1, q: "x?", kind: guard, refuse: "yes"}\n', encoding="utf-8")
    with pytest.raises(EvalSetError, match="refuse"):
        load_eval_set(path)
    assert replace(BY_ID["G1"]).refuse is True


def test_rescore_rebuilds_a_result_that_scores_the_same():
    result = _result("You're paid on the 8th and the 23rd [^1].", [_source(1, PAY)])
    scored = _score("1", result)
    row = ev._row(ev.effective(BY_ID["1"], BY_ID), result, scored, 1.0)
    rebuilt = ev.result_from_row(row)
    assert _score("1", rebuilt) == scored


def test_g4_tolerates_noise_at_the_tail_only():
    ferpa = "ferpa-adjunct-faculty-responsibilities-ia"
    def src(n, slug, score):
        node = _source(n, slug)
        node["score"] = score
        return node
    base = [src(1, ferpa, 0.36), src(2, "academic-integrity-ia", 0.34)]
    # Seen live: one more passage just at the cutoff in one of the two runs.
    tail = base + [src(3, "extending-due-dates-ia", 0.336)]
    assert ev.sources_match(tail, base)[0]
    # A different source high in the list is a real difference.
    swapped = [src(1, "pay-dates-for-worldwide-online-instructors-ia", 0.36), base[1]]
    ok, detail = ev.sources_match(swapped, base)
    assert not ok and "differ above the tail" in detail
