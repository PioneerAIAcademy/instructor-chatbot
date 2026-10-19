"""Retrieval eval (CLAUDE.md §7 Phase 2): the §10 questions through the
production retriever plus rerank.

    poetry run python scripts/eval_retrieval.py
    poetry run python scripts/eval_retrieval.py --ids 1 5 21

LIVE AND BILLABLE: per question, one OpenAI query embedding, one Pinecone
query, and one Voyage rerank. No LLM answers. Read-only against Pinecone.

For every non-guard question it reports:
- the rank of the first expected chunk after rerank, and hit@5 (any expected
  document in the top 5 chunks, the same rule as instructor-indexer `verify`);
- why each miss happened: pushed out of the raw top 5 by rerank, retrieved
  lower and not lifted, not retrieved, rerank failed, or an error (Q15: the
  0.21 cutoff stays unless the answer eval shows the effect);
- empty context (nothing left after rerank) and any non-instructor node.

Writes tests/eval/results/<UTC timestamp>-retrieval.json (gitignored).
Exits 0 only when hit@5 >= 90%, no question has an empty context, no
non-instructor node was seen, every rerank succeeded (a failed rerank falls
back to raw order, so "after rerank" wouldn't be measured), and no question
raised. A question that raises is recorded and the run continues, so the
results file is always written. Never prints keys.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evalset import TOP_K, document_rank, hit_rank, load_eval_set  # noqa: E402

RESULTS_DIR = BACKEND_DIR / "tests" / "eval" / "results"
HIT_TARGET = 0.90


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND_DIR,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def score_question(question, retrieval: dict) -> dict:
    """One question's result row, from a run_retrieval() result. Pure."""
    from app.engine.audience_guard import is_instructor_metadata

    reranked = [meta for _, meta in retrieval["reranked"]]
    raw = [meta for _, meta in retrieval["raw"]]
    rank = hit_rank(question, reranked)
    # The guard's own rule, on the raw (pre-guard) nodes.
    non_instructor = [m.get("slug") for m in raw if not is_instructor_metadata(m)]
    return {
        "id": question.id,
        "q": question.q,
        "kind": question.kind,
        "expect": list(question.expect) or list(question.expect_url),
        "hit": rank is not None and rank <= TOP_K,
        "rank_after_rerank": rank,
        "document_rank_after_rerank": document_rank(question, reranked),
        "rank_before_rerank": hit_rank(question, raw),
        "empty_context": not reranked,
        "non_instructor_nodes": non_instructor,
        "guard_dropped": retrieval["dropped"],
        "rerank_attempted": retrieval["rerank_attempted"],
        "rerank_ok": retrieval["rerank_ok"],
        "rerank_error": retrieval["rerank_error"],
        "top5": [
            {"slug": m.get("slug"), "source": m.get("source"), "score": s}
            for s, m in retrieval["reranked"][:TOP_K]
        ],
        "kept_after_rerank": len(reranked),
        "error": None,
    }


def error_row(question, exc: BaseException) -> dict:
    """A question whose retrieval raised. Counted as a miss and fails the run."""
    return {
        "id": question.id,
        "q": question.q,
        "kind": question.kind,
        "expect": list(question.expect) or list(question.expect_url),
        "hit": False,
        "rank_after_rerank": None,
        "document_rank_after_rerank": None,
        "rank_before_rerank": None,
        "empty_context": False,
        "non_instructor_nodes": [],
        "guard_dropped": 0,
        "rerank_attempted": False,
        "rerank_ok": False,
        "rerank_error": None,
        "top5": [],
        "kept_after_rerank": 0,
        # Type and message only; no request objects, so no keys.
        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
    }


def _miss_cause(row: dict) -> str:
    """Why a question missed, for the Q15 threshold decision."""
    if row["error"]:
        return "error"
    if row["rerank_attempted"] and not row["rerank_ok"]:
        return "rerank_failed"
    before = row["rank_before_rerank"]
    if before is None:
        return "not_retrieved"
    if before <= TOP_K and row["rerank_attempted"]:
        return "lost_in_rerank"  # in the raw top 5, pushed out by rerank
    return "not_lifted"  # retrieved at rank 6-35, and rerank didn't lift it into the top 5


def summarize(rows: list[dict]) -> dict:
    """Totals and the pass/fail verdict. Pure."""
    n = len(rows)
    hits = sum(r["hit"] for r in rows)
    misses = [r for r in rows if not r["hit"]]
    causes: dict[str, list[str]] = {}
    for r in misses:
        causes.setdefault(_miss_cause(r), []).append(r["id"])
    summary = {
        "questions": n,
        "hits": hits,
        "hit_at_5": hits / n if n else 0.0,
        "target": HIT_TARGET,
        "empty_context": sum(r["empty_context"] for r in rows),
        # Counted from the raw (pre-guard) nodes; the guard drops these same nodes.
        "non_instructor_nodes": sum(len(r["non_instructor_nodes"]) for r in rows),
        # A failed rerank falls back to raw order, so its "after rerank" rank is
        # really raw similarity: the run didn't measure what it claims.
        "rerank_failures": sum(r["rerank_attempted"] and not r["rerank_ok"] for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "miss_causes": causes,
    }
    summary["passed"] = (
        n > 0
        and summary["hit_at_5"] >= HIT_TARGET
        and summary["empty_context"] == 0
        and summary["non_instructor_nodes"] == 0
        and summary["rerank_failures"] == 0
        and summary["errors"] == 0
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ids", nargs="*", help="only these question ids")
    args = parser.parse_args()

    from retrieve import prepare, run_retrieval

    from app.engine.custom_condense_plus_context import RERANK_MIN_SCORE, RERANK_MODEL, RERANK_TOP_K

    eval_set = load_eval_set()
    questions = eval_set.retrieval_questions()
    if args.ids:
        questions = [q for q in questions if q.id in set(args.ids)]
    if not questions:
        print("no matching questions")
        return 2

    index_name = prepare()  # index guard + settings, once for the whole run
    rows = []
    started = time.monotonic()
    for question in questions:
        try:
            row = score_question(question, run_retrieval(question.q, index_name))
        except Exception as exc:  # keep going: the questions already run were paid for
            row = error_row(question, exc)
        rows.append(row)
        mark = "ERROR" if row["error"] else (f"hit #{row['rank_after_rerank']}" if row["hit"] else "MISS  ")
        print(f"{question.id:>3}  {mark:<8}  {question.q}")
        if row["error"]:
            print(f"      {row['error']}")
        elif row["rerank_attempted"] and not row["rerank_ok"]:
            print(f"      RERANK FAILED ({row['rerank_error']}): ranks below are raw similarity")
        if not row["hit"] and not row["error"]:
            got = ", ".join(dict.fromkeys(t["slug"] for t in row["top5"])) or "nothing"
            before = row["rank_before_rerank"]
            print(f"      expected {', '.join(row['expect'])}")
            print(f"      before rerank: {'rank ' + str(before) if before else 'not in the top 35'}; top 5 after: {got}")

    summary = summarize(rows)
    run_at = datetime.now(timezone.utc)
    report = {
        "run_at": run_at.isoformat(),
        "git_sha": _git_sha(),
        "index": index_name,
        "rerank": {"model": RERANK_MODEL, "top_k": RERANK_TOP_K, "min_score": RERANK_MIN_SCORE},
        "hit_top_k": TOP_K,
        "duration_s": round(time.monotonic() - started, 1),
        "summary": summary,
        "results": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{run_at.strftime('%Y%m%dT%H%M%SZ')}-retrieval.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"index: {index_name}  rerank: {RERANK_MODEL} top {RERANK_TOP_K} >= {RERANK_MIN_SCORE}")
    print(f"hit@{TOP_K} after rerank: {summary['hits']}/{summary['questions']} = {summary['hit_at_5']:.0%} "
          f"(target {HIT_TARGET:.0%})")
    print(f"empty context: {summary['empty_context']}   non-instructor nodes: {summary['non_instructor_nodes']}   "
          f"rerank failures: {summary['rerank_failures']}   errors: {summary['errors']}")
    labels = {
        "lost_in_rerank": "in the raw top 5, pushed out by rerank",
        "not_lifted": "retrieved at raw rank 6-35, rerank didn't lift it into the top 5",
        "not_retrieved": "not in the raw top 35",
        "rerank_failed": "rerank failed (ranks are raw similarity)",
        "error": "retrieval raised",
    }
    for cause, ids in summary["miss_causes"].items():
        print(f"misses — {labels[cause]}: {', '.join(ids)}")
    print(f"{'PASSED' if summary['passed'] else 'FAILED'} — wrote {out.relative_to(BACKEND_DIR)}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
