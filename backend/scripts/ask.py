"""Ask the local chat API one question and print what came back.

    poetry run python main.py                      # in another terminal
    poetry run python scripts/ask.py "How do I find my ACL?"
    poetry run python scripts/ask.py --url http://localhost:8000 "..."

LIVE AND BILLABLE (it's a real chat request: embedding, rerank, LLM, and the
suggested-questions call). Parses the Vercel AI data stream (`0:"text"`,
`8:[annotations]`) and prints:

- the answer;
- each source: citation number, slug, source, role, URL;
- the trace ID;
- checks: every sign-in link carries the sign-in note, no reading claims
  ("I read/opened/checked/reviewed"), every [^N] maps to a source, and all
  sources are role=instructor.

Exits 1 if a check fails. Sends X-API-Key from API_KEYS when set; never
prints it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from evalset import contains_phrase  # noqa: E402

READING_CLAIMS = ("I read", "I opened", "I checked", "I reviewed")


def parse_stream(lines) -> tuple[str, list[dict]]:
    """(answer_text, annotations) from Vercel AI data-stream lines."""
    text: list[str] = []
    annotations: list[dict] = []
    for raw in lines:
        if not raw or ":" not in raw:
            continue
        prefix, _, payload = raw.partition(":")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if prefix.strip() == "0" and isinstance(data, str):
            text.append(data)
        elif prefix.strip() == "8" and isinstance(data, list):
            annotations.extend(d for d in data if isinstance(d, dict))
    return "".join(text), annotations


def ask(question: str, url: str, data: dict | None = None, session_id: str | None = None) -> dict:
    headers = {
        "Accept": "text/event-stream",
        "X-Session-ID": session_id or f"ask-{uuid.uuid4()}",
        "X-Timezone": "UTC",
    }
    api_key = next((k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()), "")
    if api_key:
        headers["X-API-Key"] = api_key
    body = {"messages": [{"role": "user", "content": question}], "data": data or None}
    with requests.post(f"{url.rstrip('/')}/api/v1/chat", json=body, headers=headers, stream=True, timeout=240) as resp:
        resp.raise_for_status()
        answer, annotations = parse_stream(resp.iter_lines(decode_unicode=True))
    sources = next((a["data"]["nodes"] for a in annotations if a.get("type") == "sources"), [])
    trace_id = next((a.get("trace_id") for a in annotations if a.get("trace_id")), None)
    return {"answer": answer, "sources": sources, "trace_id": trace_id, "annotations": annotations}


def check(result: dict) -> list[str]:
    """Problems with an answer, as human-readable lines. No network."""
    # The annotator's own rule (same link parser, fence handling, and labels in
    # every language), so this can't disagree with what production does.
    from app.engine.login_links import unlabeled_login_links

    answer, sources = result["answer"], result["sources"]
    problems: list[str] = []
    for link in unlabeled_login_links(answer):
        problems.append(f"sign-in link without the note: {link}")
    for phrase in READING_CLAIMS:
        if contains_phrase(answer, phrase):
            problems.append(f'reading claim: "{phrase}"')
    cited = {n for n in re.findall(r"\[\^(\d+)\]", answer)}
    known = {str(s.get("citation_node_id")) for s in sources}
    for n in sorted(cited - known, key=int):
        problems.append(f"[^{n}] has no matching source")
    for s in sources:
        role = (s.get("metadata") or {}).get("role")
        if role != "instructor":
            problems.append(f"non-instructor source: {(s.get('metadata') or {}).get('slug')} role={role!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("question")
    parser.add_argument("--url", default=os.getenv("CHAT_API_URL", "http://localhost:8000"))
    args = parser.parse_args()

    result = ask(args.question, args.url)
    print(f"Q: {args.question}\n")
    print(result["answer"])
    print("\nSOURCES")
    for s in result["sources"]:
        meta = s.get("metadata") or {}
        print(f"  [^{s.get('citation_node_id')}] {meta.get('slug')}  ({meta.get('source')}, role={meta.get('role')})")
        print(f"        {s.get('url')}")
    print(f"\ntrace: {result['trace_id']}")
    problems = check(result)
    print("\nCHECKS: " + ("ok" if not problems else "FAILED"))
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
