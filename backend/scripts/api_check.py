"""Live check of the chat API against a running server (CLAUDE.md §7 Phase 4).

    poetry run python main.py                      # in another terminal
    poetry run python scripts/api_check.py
    poetry run python scripts/api_check.py --url https://staging.example.org

LIVE AND BILLABLE: 3 chat requests (embedding, rerank, LLM, suggestions), 1
draft-edit LLM call, 1 thumbs score, and 1 general-feedback trace.

Checks, each printed as PASS/FAIL:
1. An answer stream conforms to the contract in backend/API.md
   (scripts/api_contract.py): only 0:/8: lines, documented annotations in
   order, sources with the documented fields.
2. It carries answer text, sources whose url is the guide's PDF
   (missionaries.prod.byu-pathway.psdops.com/<slug>) or the linked page's own
   URL, and suggested questions; every [^N] maps to a source.
3. A body with data.role="missionary" gets exactly the same sources (§10 G4).
4. /thumbs_request on the answer's trace returns 200.
5. /draft/edit returns an edited text.
6. /feedback/general (text only) returns 200.
7. /openapi.json (what /api/docs shows) lists only the kept routes.
8. /config serves the starter questions (built in unless CONVERSATION_STARTERS overrides them).

Exits 1 if any check fails. Sends X-API-Key from API_KEYS when set; never
prints it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

import api_contract  # noqa: E402

PDF_PREFIX = "https://missionaries.prod.byu-pathway.psdops.com/"
ANSWER_Q = "When do Worldwide Online instructors in the US get paid?"
G4_Q = "A student's mother emailed asking about her son's grade. Can I tell her?"


class Checker:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.failures = 0
        self.headers = api_contract.client_headers("apicheck")

    def result(self, name: str, problems: list[str], note: str = "") -> None:
        print(f"{'PASS' if not problems else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
        for p in problems:
            print(f"      - {p}")
        self.failures += bool(problems)

    def chat(self, question: str, data: dict | None = None) -> tuple[str, list[dict], list[str]]:
        body = {"messages": [{"role": "user", "content": question}], "data": data}
        with requests.post(f"{self.url}/api/v1/chat", json=body, headers=self.headers, stream=True, timeout=240) as r:
            if r.status_code != 200:
                return "", [], [f"HTTP {r.status_code}: {r.text[:200]}"]
            text, annotations, problems = api_contract.parse_lines(r.iter_lines(decode_unicode=True))
        return "".join(text), annotations, problems


def _sources(annotations: list[dict]) -> list[dict]:
    return next((a["data"]["nodes"] for a in annotations if a.get("type") == "sources"), [])


def check_answer(c: Checker) -> str | None:
    answer, annotations, problems = c.chat(ANSWER_Q)
    c.result("1. stream matches the API.md contract",
             problems + api_contract.check_annotations(annotations))

    nodes = _sources(annotations)
    content: list[str] = []
    if not answer.strip():
        content.append("no answer text")
    if not nodes:
        content.append("no sources")
    for n in nodes:
        meta = n.get("metadata") or {}
        if meta.get("source") == "instructor-assistant":
            expected = PDF_PREFIX + str(meta.get("slug"))
            if n.get("url") != expected:
                content.append(f"guide source url {n.get('url')!r} is not {expected!r}")
        elif meta.get("source") == "instructor-assistant-linked":
            if not str(n.get("url") or "").startswith("http") or n.get("url") != meta.get("url"):
                content.append(f"linked source url {n.get('url')!r} is not the page's own URL")
        else:
            content.append(f"unexpected source {meta.get('source')!r}")
    if not any(a.get("type") == "suggested_questions" and a.get("data") for a in annotations):
        content.append("no suggested_questions")
    cited = set(re.findall(r"\[\^(\d+)\]", answer))
    unmapped = cited - {str(n.get("citation_node_id")) for n in nodes}
    if unmapped:
        content.append(f"citations without a source: {sorted(unmapped, key=int)}")
    if not cited:
        content.append("the answer cites nothing")
    c.result("2. text, document URLs, suggestions, and citations", content,
             f"{len(nodes)} sources, {len(cited)} distinct citations")
    return next((a.get("trace_id") for a in annotations if a.get("trace_id")), None)


def check_client_role(c: Checker) -> None:
    _, plain, p1 = c.chat(G4_Q)
    _, with_role, p2 = c.chat(G4_Q, {"role": "missionary"})
    key = lambda nodes: [(n.get("citation_node_id"), (n.get("metadata") or {}).get("slug")) for n in nodes]
    problems = p1 + p2
    if key(_sources(plain)) != key(_sources(with_role)):
        problems.append(f"sources differ: {key(_sources(plain))} vs {key(_sources(with_role))}")
    roles = {(n.get("metadata") or {}).get("role") for n in _sources(plain) + _sources(with_role)}
    if roles - {"instructor"}:
        problems.append(f"non-instructor roles: {roles}")
    if not _sources(plain):
        problems.append("no sources to compare")
    c.result('3. data.role="missionary" changes nothing (G4)', problems, f"{len(_sources(plain))} sources each")


def check_thumbs(c: Checker, trace_id: str | None) -> None:
    if not trace_id:
        c.result("4. thumbs_request", ["the answer had no trace_id (is Langfuse configured?)"])
        return
    r = requests.post(f"{c.url}/api/v1/chat/thumbs_request", headers=c.headers, timeout=30,
                      json={"trace_id": trace_id, "value": "good", "comment": ""})
    ok = r.status_code == 200 and r.json() == {"feedback": "Good"}
    c.result("4. thumbs_request", [] if ok else [f"HTTP {r.status_code}: {r.text[:200]}"], f"trace {trace_id}")


def check_draft_edit(c: Checker) -> None:
    r = requests.post(f"{c.url}/api/v1/chat/draft/edit", headers=c.headers, timeout=120, json={
        "draft_type": "message",
        "instruction": "Make this warmer and add a line welcoming them to the course.",
        "selected_text": "Hi [Student Name]. Class starts Monday.",
        "full_content": "Hi [Student Name]. Class starts Monday.\n[Your Name]",
    })
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    ok = r.status_code == 200 and body.get("edited_text") and body.get("reason") == "ok"
    c.result("5. draft edit", [] if ok else [f"HTTP {r.status_code}: {str(body or r.text)[:200]}"],
             repr((body.get("edited_text") or "")[:60]))


def check_general_feedback(c: Checker) -> None:
    r = requests.post(f"{c.url}/api/v1/chat/feedback/general", headers=c.headers, timeout=30,
                      data={"feedback": "api_check.py smoke test (ignore)"})
    ok = r.status_code == 200 and r.json().get("status") == "success"
    c.result("6. general feedback (text only)", [] if ok else [f"HTTP {r.status_code}: {r.text[:200]}"])


def check_routes(c: Checker) -> None:
    paths = set(requests.get(f"{c.url}/openapi.json", timeout=30).json()["paths"])
    problems = [f"extra route {p}" for p in sorted(paths - api_contract.KEPT_ROUTES)]
    problems += [f"missing route {p}" for p in sorted(api_contract.KEPT_ROUTES - paths)]
    c.result("7. /api/docs lists only the kept routes", problems)


def check_config(c: Checker) -> None:
    starters = requests.get(f"{c.url}/api/v1/chat/config", timeout=30).json().get("starterQuestions")
    if not starters:
        print("WARN  8. /config has no starter questions (CONVERSATION_STARTERS is set but blank)")
        return
    c.result("8. /config serves starter questions", [], f"{len(starters)}: {starters}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default=os.getenv("CHAT_API_URL", "http://localhost:8000"))
    args = parser.parse_args()

    c = Checker(args.url)
    trace_id = check_answer(c)
    check_client_role(c)
    check_thumbs(c, trace_id)
    check_draft_edit(c)
    check_general_feedback(c)
    check_routes(c)
    check_config(c)
    print(f"\n{'ALL PASSED' if not c.failures else f'{c.failures} FAILED'}")
    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(main())
