"""Rubric eval: questions through the local chat API, each answer judged
against a checklist by an LLM.

    poetry run python main.py > server.log 2>&1        # in another terminal
    poetry run python scripts/eval_rubric.py tests/eval/team/rubric.yaml
    poetry run python scripts/eval_rubric.py tests/eval/team/rubric.yaml --ids T1 T5
    poetry run python scripts/eval_rubric.py tests/eval/team/rubric.yaml --rejudge <results.json>

LIVE AND BILLABLE: one full chat request per question, plus one judge call
(LLM_JUDGE_MODEL, default gpt-4o). --rejudge re-judges the answers saved in a
results file against the current checklists, with no chat requests. The judge sees the
passages the assistant was given (saved with each answer), so it can tell whether a link,
form, or step is in the guides.

The checklist file (YAML):

    questions:
      - id: T5
        q: I have lost access to Canvas and can't see my course.
        rubric:
          - Asks whether the instructor can't log in at all, or can log in but the course is missing.
          - text: Doesn't send the instructor to the student escalation form for their own access.
            required: true

An item is required unless `required: false`. A question passes when the
judge marks every required item met. Results go to <checklist folder>/results/
<UTC timestamp>-rubric.json (put the checklists somewhere gitignored if they
hold internal material). Sessions are `eval-<run id>`, so traces are tagged
`eval` (CLAUDE.md §9.1). Never prints keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_answers import ask_with_retry  # noqa: E402

JUDGE_PROMPT = """You grade an answer from the BYU-Pathway Instructor Assistant, a chatbot for
online instructors, against a checklist. For each item, decide whether the answer meets it.
Judge what the answer says, not what it should have known. An item that says the answer
must NOT do something is met when the answer doesn't do it. A clarifying question counts
only if the answer actually asks it. "The guides" means the CONTEXTS below, the passages the
assistant was given: a link, form, step, or fact counts as in the guides only if a context
contains it. Reply with JSON only:
{"items": [{"n": <item number>, "met": <true|false>, "why": "<one short reason>"}]}"""


def load_checklists(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text())
    questions = []
    for raw in data["questions"]:
        items = []
        for item in raw.get("rubric", []):
            if isinstance(item, str):
                items.append({"text": item, "required": True})
            else:
                items.append({"text": item["text"], "required": item.get("required", True)})
        questions.append({"id": str(raw["id"]), "q": raw["q"], "rubric": items})
    return questions


def contexts_of(sources: list[dict]) -> list[dict]:
    """The passages the assistant was given, as saved with each answer."""
    return [
        {
            "n": s.get("citation_node_id"),
            "title": (s.get("metadata") or {}).get("title"),
            "url": s.get("url"),
            "text": s.get("text") or "",
        }
        for s in sources or []
    ]


def judge(question: str, answer: str, rubric: list[dict], model: str, contexts: list[dict]) -> dict:
    from openai import OpenAI

    checklist = "\n".join(f"{n}. {item['text']}" for n, item in enumerate(rubric, 1))
    context_text = "\n\n".join(
        f"[{c['n']}] {c['title'] or ''} ({c['url'] or ''})\n{c['text']}" for c in contexts
    ) or "(none)"
    try:
        reply = OpenAI(timeout=90).chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": f"QUESTION\n{question}\n\nCONTEXTS\n{context_text}\n\nANSWER\n{answer}\n\nCHECKLIST\n{checklist}"},
            ],
        )
        verdict = json.loads(reply.choices[0].message.content or "{}")
        by_n = {int(i["n"]): i for i in verdict.get("items", []) if "n" in i}
        items = [
            {**item, "met": bool(by_n.get(n, {}).get("met")), "why": by_n.get(n, {}).get("why", "not judged")}
            for n, item in enumerate(rubric, 1)
        ]
        return {"items": items}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200], "items": [{**i, "met": False, "why": "judge error"} for i in rubric]}


def grade(question: dict, answer: str | None, error: str | None, model: str, contexts: list[dict]) -> dict:
    if error or not answer:
        items = [{**i, "met": False, "why": error or "no answer"} for i in question["rubric"]]
        return {"items": items, "passed": False}
    verdict = judge(question["q"], answer, question["rubric"], model, contexts)
    passed = "error" not in verdict and all(i["met"] for i in verdict["items"] if i["required"])
    return {**verdict, "passed": passed}


def report(rows: list[dict]) -> None:
    for row in rows:
        missed = [i for i in row["items"] if not i["met"]]
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"{mark}  {row['id']:4} {row['q'][:70]}")
        for item in missed:
            flag = "" if item["required"] else " (optional)"
            print(f"        missed{flag}: {item['text'][:90]} — {item['why'][:80]}")
    total = len(rows)
    passed = sum(r["passed"] for r in rows)
    met = sum(i["met"] for r in rows for i in r["items"])
    items = sum(len(r["items"]) for r in rows)
    print(f"\n{passed}/{total} questions pass; {met}/{items} checklist items met")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("checklists", type=Path)
    parser.add_argument("--ids", nargs="*", help="only these question ids")
    parser.add_argument("--url", default=os.getenv("CHAT_API_URL", "http://localhost:8000"))
    parser.add_argument("--rejudge", type=Path, help="re-judge a saved results file; no chat requests")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    model = os.getenv("LLM_JUDGE_MODEL", "gpt-4o")
    questions = load_checklists(args.checklists)
    if args.ids:
        questions = [q for q in questions if q["id"] in set(args.ids)]
    if not questions:
        print("no matching questions")
        return 2

    saved: dict[str, dict] = {}
    if args.rejudge:
        saved = {r["id"]: r for r in json.loads(args.rejudge.read_text())["rows"]}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"eval-{run_id}"
    rows = []
    for question in questions:
        t0 = time.monotonic()
        if args.rejudge:
            prior = saved.get(question["id"], {})
            answer, error = prior.get("answer"), prior.get("error")
            contexts = prior.get("contexts") or []
            if question["id"] not in saved:
                error = "not in the saved results"
        else:
            from ask import ask

            result = ask_with_retry(ask, SimpleNamespace(q=question["q"], data=None), args.url, session_id)
            answer, error = result.get("answer"), result.get("error")
            contexts = contexts_of(result.get("sources") or [])
        graded = grade(question, answer, error, model, contexts)
        rows.append({
            "id": question["id"], "q": question["q"], "answer": answer, "error": error,
            "contexts": contexts,
            "seconds": round(time.monotonic() - t0, 1), **graded,
        })
        print(f"  {question['id']}: {'pass' if graded['passed'] else 'fail'}", flush=True)

    out_dir = args.checklists.parent / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{run_id}-rubric.json"
    out.write_text(json.dumps({
        "run_id": run_id, "judge": model, "checklists": str(args.checklists),
        "rejudged_from": str(args.rejudge) if args.rejudge else None, "rows": rows,
    }, indent=1, ensure_ascii=False))
    print()
    report(rows)
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
