"""Answer eval (CLAUDE.md §7 Phase 6): the §10 questions through the local
chat API, with deterministic checks on each answer.

    poetry run python main.py > server.log 2>&1        # in another terminal
    poetry run python scripts/eval_answers.py
    poetry run python scripts/eval_answers.py --ids 1 5 G4
    poetry run python scripts/eval_answers.py --rescore tests/eval/results/<file>-answers.json
    RUN_LLM_JUDGE=1 poetry run python scripts/eval_answers.py   # adds a groundedness score

LIVE AND BILLABLE: one full chat request per question (embedding, rerank,
the answer, and the suggested-questions call), plus one judge call per
question with RUN_LLM_JUDGE=1. Read-only against Pinecone.

Every request uses X-Session-ID `eval-<run id>`, so its trace is tagged `eval`
and `eval_run:<run id>` (§9.1) and dashboards can leave it out. Each trace also
gets an `eval_pass` score (1 or 0) unless --no-scores is given.

Checks per question (§7 Phase 6), each recorded as ok / failed / skipped:
1. cites_expected     a cited source is an expected document (slug or URL)
2. citations_resolve  every [^N] in the answer matches a returned source
3. instructor_sources every source is role=instructor from an allowed source
4. must_include       every phrase group matches (any phrase in the group)
5. must_not           no forbidden phrase (defaults plus the question's own);
                      a phrase the question itself contains doesn't count
6. sign_in_labels     every sign-in link outside a draft has its note
7. refusal            questions marked `refuse` refuse and cite nothing
Plus, by kind: draft (a ```message / ```email fence with text and no [^N]
inside), same_sources (G4: the same sources as the question in same_as,
apart from retrieval noise at the tail; see sources_match),
and stream (the request worked and the stream matched API.md).

Passes when >= 85% of the answer questions (every kind but guard) pass all
their checks and every guard question does. A question that errors fails and
the run continues, so the results file is always written:
tests/eval/results/<UTC timestamp>-answers.json (gitignored). The optional
judge reports only and never changes a result. Never prints keys.

--rescore re-checks the answers saved in a results file against the current
questions.yaml, with no requests (free). Use it after fixing a check, to see
what the fix changes without paying for new answers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evalset import Question, contains_phrase, load_eval_set, normal_url  # noqa: E402

RESULTS_DIR = BACKEND_DIR / "tests" / "eval" / "results"
ANSWER_TARGET = 0.85
GUARD_TARGET = 1.0
_CITATION_RE = re.compile(r"\[\^(\d+)\]")
DRAFT_TAGS = ("message", "email")

# What a refusal or a "not in the guides" answer says (the prompt's GROUNDING
# case 3 and OUT OF SCOPE). English: the eval questions are English.
_REFUSAL_RE = re.compile(
    r"\b(?:"
    r"can(?:no|')t help|can only help|only (?:help|answer|assist)|"
    r"(?:do not|don't|doesn't|does not) (?:have|cover|include|contain|mention|provide)|"
    r"(?:couldn't|could not|can't|cannot) find|"
    r"(?:isn't|is not|aren't|are not|not) (?:covered|included|mentioned|available)|"
    r"outside (?:of )?(?:my|the|what)|not (?:something|able)|unable to|"
    r"no (?:information|details|guidance)"
    r")",
    re.IGNORECASE,
)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND_DIR,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


# --- pure scoring (no network; tests/test_eval_answers.py) ---------------------------


def effective(question: Question, by_id: dict[str, Question]) -> Question:
    """G4-style guards check what their same_as question checks, when they
    have no expect or must_include of their own."""
    ref = by_id.get(question.same_as or "")
    if ref is None:
        return question
    from dataclasses import replace

    return replace(
        question,
        expect=question.expect or ref.expect,
        expect_url=question.expect_url or ref.expect_url,
        must_include=question.must_include or ref.must_include,
    )


def cited_sources(answer: str, sources: list[dict]) -> list[dict]:
    """The sources the answer's [^N] markers point at, in citation order."""
    by_number = {str(s.get("citation_node_id")): s for s in sources}
    numbers = dict.fromkeys(_CITATION_RE.findall(answer or ""))
    return [by_number[n] for n in numbers if n in by_number]


def is_refusal(answer: str) -> bool:
    return bool(_REFUSAL_RE.search((answer or "").replace("’", "'")))


def draft_problems(answer: str) -> list[str]:
    from app.utils.links import fence_info, split_fences

    problems: list[str] = []
    drafts = []
    for in_fence, segment in split_fences(answer or ""):
        if not in_fence:
            continue
        lines = segment.splitlines()
        if (fence_info(lines[0]) or "").strip().lower() in DRAFT_TAGS:
            drafts.append("\n".join(lines[1:-1]))
    if not drafts:
        return [f"no ```{' / ```'.join(DRAFT_TAGS)} fence"]
    for body in drafts:
        if not body.strip():
            problems.append("the draft fence is empty")
        if _CITATION_RE.search(body):
            problems.append("a [^N] marker is inside the draft")
    return problems


def _check(ok: bool, detail: str = "") -> dict:
    return {"status": "ok" if ok else "failed", "detail": "" if ok else detail}


def _skip(detail: str) -> dict:
    return {"status": "skipped", "detail": detail}


def sources_match(mine: list[dict], theirs: list[dict]) -> tuple[bool, str]:
    """G4: did the client-sent role change the sources? Two separate requests
    for the same question don't retrieve byte-identical lists: the scores
    shift slightly between calls (seen live: 0.3443 vs 0.3368 for the same
    passage), so a passage right at the cutoff can come or go. The lists
    match when every source that differs ranks below every source the two
    lists share, in its own list: noise at the tail, not a different answer
    basis. The audience itself is checked by instructor_sources, and the
    filter's independence from the client role by tests/test_chat_api.py
    (offline, exact)."""

    def by_id(nodes: list[dict]) -> dict[str, float]:
        return {str(n.get("id")): float(n.get("score") or 0.0) for n in nodes}

    a, b = by_id(mine), by_id(theirs)
    if set(a) == set(b):
        return True, f"{len(a)} identical sources"
    shared = set(a) & set(b)
    if not shared:
        return False, f"{len(a)} sources vs {len(b)}, none shared"
    above = []
    for scores in (a, b):
        lowest_shared = min(scores[i] for i in shared)
        above += [i for i in set(scores) - shared if scores[i] > lowest_shared]
    if above:
        return False, f"{len(a)} sources vs {len(b)}; differ above the tail: {', '.join(sorted(above))}"
    return True, f"{len(a)} vs {len(b)} sources, differing only at the tail"


def score_answer(
    question: Question,
    result: dict,
    *,
    default_must_not: tuple[str, ...] = (),
    reference: dict | None = None,
) -> dict:
    """One question's checks, from an ask() result. Pure.

    `question` should already be effective(). `reference` is the result of the
    question named in same_as, when there is one."""
    from app.engine.audience_guard import is_instructor_metadata
    from app.engine.login_links import unlabeled_login_links

    checks: dict[str, dict] = {}
    if result.get("error"):
        checks["stream"] = _check(False, result["error"])
        return {"checks": checks, "passed": False}
    answer = result.get("answer") or ""
    sources = result.get("sources") or []
    problems = list(result.get("contract_problems") or [])
    if not answer.strip():
        problems.append("empty answer")
    checks["stream"] = _check(not problems, "; ".join(problems))

    cited = cited_sources(answer, sources)
    if question.expect or question.expect_url:
        urls = {normal_url(u) for u in question.expect_url}
        hit = any(
            str((s.get("metadata") or {}).get("slug") or "").lower() in question.expect
            or (urls and normal_url(str(s.get("url") or "")) in urls)
            for s in cited
        )
        got = ", ".join(str((s.get("metadata") or {}).get("slug")) for s in cited) or "nothing cited"
        checks["cites_expected"] = _check(hit, f"cited {got}")
    else:
        checks["cites_expected"] = _skip("no expected document")

    known = {str(s.get("citation_node_id")) for s in sources}
    dangling = sorted(set(_CITATION_RE.findall(answer)) - known, key=int)
    checks["citations_resolve"] = _check(not dangling, ", ".join(f"[^{n}]" for n in dangling) + " match no source")

    outside = [
        f"{(s.get('metadata') or {}).get('slug')} role={(s.get('metadata') or {}).get('role')!r} "
        f"source={(s.get('metadata') or {}).get('source')!r}"
        for s in sources if not is_instructor_metadata(s.get("metadata") or {})
    ]
    checks["instructor_sources"] = _check(not outside, "; ".join(outside))

    if question.must_include:
        missing = [group for group in question.must_include if not any(contains_phrase(answer, p) for p in group)]
        checks["must_include"] = _check(not missing, "missing " + "; ".join(" or ".join(f'"{p}"' for p in g) for g in missing))
    else:
        checks["must_include"] = _skip("no phrases required")

    forbidden = [
        p for p in (*default_must_not, *question.must_not)
        if contains_phrase(answer, p) and not contains_phrase(question.q, p)
    ]
    checks["must_not"] = _check(not forbidden, "contains " + ", ".join(f'"{p}"' for p in forbidden))

    unlabeled = unlabeled_login_links(answer)
    checks["sign_in_labels"] = _check(not unlabeled, "no sign-in note on " + ", ".join(unlabeled))

    if question.refuse:
        why = []
        if not is_refusal(answer):
            why.append("doesn't refuse or say it isn't in the guides")
        if cited:
            why.append("cites a source")
        checks["refusal"] = _check(not why, "; ".join(why))
    else:
        checks["refusal"] = _skip("not a refusal question")

    if question.kind == "draft":
        draft = draft_problems(answer)
        checks["draft"] = _check(not draft, "; ".join(draft))

    if question.same_as:
        if reference is None or reference.get("error"):
            checks["same_sources"] = _check(False, f"question {question.same_as} didn't run")
        else:
            ok, detail = sources_match(sources, reference.get("sources") or [])
            checks["same_sources"] = _check(ok, f"{detail} (vs question {question.same_as})")

    passed = all(c["status"] != "failed" for c in checks.values())
    return {"checks": checks, "passed": passed}


def summarize(rows: list[dict]) -> dict:
    answers = [r for r in rows if r["kind"] != "guard"]
    guards = [r for r in rows if r["kind"] == "guard"]

    def rate(group: list[dict]) -> float:
        return sum(r["passed"] for r in group) / len(group) if group else 1.0

    failed_checks: dict[str, list[str]] = {}
    for r in rows:
        for name, c in r["checks"].items():
            if c["status"] == "failed":
                failed_checks.setdefault(name, []).append(r["id"])
    summary = {
        "answer_questions": len(answers),
        "answers_passed": sum(r["passed"] for r in answers),
        "answer_pass_rate": rate(answers),
        "guard_questions": len(guards),
        "guards_passed": sum(r["passed"] for r in guards),
        "guard_pass_rate": rate(guards),
        "errors": sum(1 for r in rows if r.get("error")),
        "failed_checks": failed_checks,
    }
    summary["passed"] = bool(rows) and summary["answer_pass_rate"] >= ANSWER_TARGET and (
        summary["guard_pass_rate"] >= GUARD_TARGET
    )
    return summary


# --- live --------------------------------------------------------------------------


def ask_with_retry(ask: Callable[..., dict], question: Question, url: str, session_id: str,
                   *, tries: int = 4, sleep: Callable[[float], None] = time.sleep) -> dict:
    """ask(), waiting out the chat route's 10/minute limit (HTTP 429) instead
    of failing the question. Any other failure becomes {"error": ...}."""
    import requests

    for attempt in range(tries):
        try:
            return ask(question.q, url, data=question.data or None, session_id=session_id)
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is not None and resp.status_code == 429 and attempt + 1 < tries:
                wait = float(resp.headers.get("Retry-After") or 60)
                print(f"      rate limited; waiting {wait:.0f}s")
                sleep(min(wait, 90))
                continue
            return {"error": f"HTTP {resp.status_code if resp is not None else '?'}"}
        except Exception as exc:  # keep going: the questions already run were paid for
            return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return {"error": "rate limited"}


JUDGE_PROMPT = """You check an answer from the BYU-Pathway Instructor Assistant against the
numbered contexts it was given. Reply with JSON only:
{"grounded": <0.0-1.0, the share of the answer's factual claims that the contexts support>,
 "unsupported": [<short quotes of claims the contexts don't support>],
 "student_portal_as_instructor_action": <true if it tells the INSTRUCTOR to do something in the
   Student Portal, which is a student tool>}
A refusal or "not in the guides" answer with no factual claims is grounded 1.0."""


def judge(question: str, answer: str, sources: list[dict]) -> dict:
    """Optional LLM groundedness check (RUN_LLM_JUDGE=1). Reports only."""
    from openai import OpenAI

    contexts = "\n\n".join(f"[{s.get('citation_node_id')}] {s.get('text') or ''}" for s in sources) or "(none)"
    model = os.getenv("LLM_JUDGE_MODEL", "gpt-4o")
    try:
        reply = OpenAI(timeout=60).chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": f"QUESTION\n{question}\n\nCONTEXTS\n{contexts}\n\nANSWER\n{answer}"},
            ],
        )
        verdict = json.loads(reply.choices[0].message.content or "{}")
        return {"model": model, **verdict}
    except Exception as exc:
        return {"model": model, "error": f"{type(exc).__name__}: {exc}"[:200]}


def post_score(trace_id: str | None, passed: bool, run_id: str) -> bool:
    """eval_pass (1/0) on the question's trace (§9.1). An upsert, so re-posting
    is harmless."""
    if not trace_id:
        return False
    try:
        from app.langfuse import langfuse

        langfuse.create_score(
            score_id=f"{trace_id}_eval_pass", trace_id=trace_id, name="eval_pass",
            value=1 if passed else 0, data_type="NUMERIC", comment=f"eval_run:{run_id}",
        )
        return True
    except Exception:
        return False


def _row(question: Question, result: dict, scored: dict, seconds: float) -> dict:
    sources = result.get("sources") or []
    return {
        "id": question.id,
        "kind": question.kind,
        "q": question.q,
        "passed": scored["passed"],
        "checks": scored["checks"],
        "error": result.get("error"),
        "contract_problems": result.get("contract_problems") or [],
        "answer": result.get("answer"),
        "cited": [str((s.get("metadata") or {}).get("slug")) for s in cited_sources(result.get("answer") or "", sources)],
        "sources": [
            {"n": s.get("citation_node_id"), "id": s.get("id"), "slug": (s.get("metadata") or {}).get("slug"),
             "source": (s.get("metadata") or {}).get("source"), "role": (s.get("metadata") or {}).get("role"),
             "url": s.get("url"), "score": s.get("score")}
            for s in sources
        ],
        "trace_id": result.get("trace_id"),
        "seconds": round(seconds, 1),
    }


def result_from_row(row: dict) -> dict:
    """Rebuild an ask() result from a saved results row (for --rescore)."""
    sources = [
        {"id": s.get("id"), "citation_node_id": s.get("n"), "url": s.get("url"), "score": s.get("score"),
         "metadata": {"slug": s.get("slug"), "source": s.get("source"), "role": s.get("role"), "url": s.get("url")}}
        for s in row.get("sources") or []
    ]
    return {"answer": row.get("answer"), "sources": sources, "error": row.get("error"),
            "contract_problems": row.get("contract_problems") or [], "trace_id": row.get("trace_id")}


def rescore(path: Path) -> int:
    saved = json.loads(path.read_text(encoding="utf-8"))
    eval_set = load_eval_set()
    by_id = {q.id: q for q in eval_set.questions}
    results = {row["id"]: result_from_row(row) for row in saved["results"]}
    rows = []
    for row in saved["results"]:
        if row["id"] not in by_id:
            continue
        q = effective(by_id[row["id"]], by_id)
        scored = score_answer(q, results[row["id"]], default_must_not=eval_set.default_must_not,
                              reference=results.get(q.same_as or ""))
        rows.append({**row, "kind": q.kind, "passed": scored["passed"], "checks": scored["checks"]})
        was = "PASS" if row["passed"] else "FAIL"
        now = "PASS" if scored["passed"] else "FAIL"
        print(f"{q.id:>3}  {now}" + (f"  (was {was})" if was != now else ""))
        for name, c in scored["checks"].items():
            if c["status"] == "failed":
                print(f"      {name}: {c['detail']}")
    summary = summarize(rows)
    print(f"\nrescored {path.name}: answers {summary['answers_passed']}/{summary['answer_questions']} = "
          f"{summary['answer_pass_rate']:.0%}, guards {summary['guards_passed']}/{summary['guard_questions']} — "
          f"{'PASSED' if summary['passed'] else 'FAILED'}")
    return 0 if summary["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ids", nargs="*", help="only these question ids (a same_as reference is added)")
    parser.add_argument("--url", default=os.getenv("CHAT_API_URL", "http://localhost:8000"))
    parser.add_argument("--no-scores", action="store_true", help="don't post eval_pass scores to Langfuse")
    parser.add_argument("--rescore", type=Path, help="re-check a saved results file; sends nothing")
    args = parser.parse_args()
    if args.rescore:
        return rescore(args.rescore)

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    from ask import ask

    eval_set = load_eval_set()
    by_id = {q.id: q for q in eval_set.questions}
    questions = list(eval_set.questions)
    if args.ids:
        wanted = set(args.ids)
        wanted |= {by_id[i].same_as for i in wanted if i in by_id and by_id[i].same_as}
        questions = [q for q in questions if q.id in wanted]
    if not questions:
        print("no matching questions")
        return 2
    # A same_as reference runs before the question that compares against it.
    questions.sort(key=lambda q: q.same_as is not None)

    run_at = datetime.now(timezone.utc)
    run_id = run_at.strftime("%Y%m%dT%H%M%SZ")
    session_id = f"eval-{run_id}"
    use_judge = os.getenv("RUN_LLM_JUDGE") == "1"
    results: dict[str, dict] = {}
    rows: list[dict] = []
    started = time.monotonic()
    for question in questions:
        q = effective(question, by_id)
        t0 = time.monotonic()
        result = ask_with_retry(ask, q, args.url, session_id)
        results[q.id] = result
        scored = score_answer(q, result, default_must_not=eval_set.default_must_not,
                              reference=results.get(q.same_as or ""))
        row = _row(q, result, scored, time.monotonic() - t0)
        if use_judge and not result.get("error"):
            row["judge"] = judge(q.q, result.get("answer") or "", result.get("sources") or [])
        if not args.no_scores:
            row["score_posted"] = post_score(result.get("trace_id"), row["passed"], run_id)
        rows.append(row)
        print(f"{q.id:>3}  {'PASS' if row['passed'] else 'FAIL'}  {q.kind:<7} {q.q}")
        for name, c in row["checks"].items():
            if c["status"] == "failed":
                print(f"      {name}: {c['detail']}")
        if "judge" in row:
            j = row["judge"]
            print(f"      judge: grounded={j.get('grounded')}" + (f" error={j['error']}" if j.get("error") else ""))

    if not args.no_scores:
        try:
            from app.langfuse import langfuse

            langfuse.flush()
        except Exception:
            pass

    summary = summarize(rows)
    report = {
        "run_at": run_at.isoformat(),
        "run_id": run_id,
        "session_id": session_id,
        "git_sha": _git_sha(),
        "index": os.getenv("PINECONE_INDEX_NAME", ""),
        "model": os.getenv("MODEL", ""),
        "judge": os.getenv("LLM_JUDGE_MODEL", "gpt-4o") if use_judge else None,
        "duration_s": round(time.monotonic() - started, 1),
        "summary": summary,
        "results": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{run_id}-answers.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"answers: {summary['answers_passed']}/{summary['answer_questions']} = "
          f"{summary['answer_pass_rate']:.0%} (target {ANSWER_TARGET:.0%})")
    print(f"guards:  {summary['guards_passed']}/{summary['guard_questions']} = "
          f"{summary['guard_pass_rate']:.0%} (target {GUARD_TARGET:.0%})   errors: {summary['errors']}")
    for name, ids in summary["failed_checks"].items():
        print(f"failed {name}: {', '.join(ids)}")
    print(f"{'PASSED' if summary['passed'] else 'FAILED'} — wrote {out.relative_to(BACKEND_DIR)} "
          f"(Langfuse session {session_id})")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
