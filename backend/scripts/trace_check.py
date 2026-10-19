"""Live check of tracing (CLAUDE.md §7 Phase 5) against a running server.

    poetry run python main.py > server.log 2>&1        # in another terminal
    poetry run python scripts/trace_check.py --log server.log

LIVE AND BILLABLE: 3 chat requests and 1 thumbs score, then read-only queries
to Langfuse with the keys in backend/.env. It reads back through the APIs
Langfuse supports for new organizations: GET /api/public/v2/observations
(observations, input/output, metadata), GET /api/public/v2/metrics (tags,
trace name), and GET /api/public/v3/scores (scores). The SDK's fetch_trace uses
a legacy endpoint that returns 410 for this organization.

Checks, each PASS/FAIL:
1. The question's trace is named `chat` and has every §9.1 tag.
2. Its root observation has the §9.1 metadata keys.
3. `retrieval-orchestrator` sits under the root, and a `rag-llm` generation
   (the LlamaIndex bridge) under it.
4. A thumbs-down posted on the trace lands as `user_feedback`, with its comment
   redacted.
5. Eval traffic (X-Session-ID `eval-<run>`) carries `eval` and `eval_run:<run>`.
6. A question with an email and a student ID reaches Langfuse masked, in the
   root input and in the rag-llm prompt.
7. No key or secret from .env appears in any fetched observation or in the
   server log (--log). Only booleans are printed, never values.
8. Tags added when a trace finishes reach the trace: a draft edit's
   `outcome:*` tag (the same path `guard:audience_leak` takes).

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

import api_contract  # noqa: E402

QUESTION = "When do Worldwide Online instructors in the US get paid?"
PII_EMAIL = "jordan.sample@example.org"
PII_ID = "90817263"
PII_QUESTION = f"Student {PII_ID} ({PII_EMAIL}) asked when instructors get paid. What should I tell them?"
THUMBS_COMMENT_ID = "55443322"
# LANGFUSE_PUBLIC_KEY isn't a secret, and Langfuse itself records it in span metadata.
SECRET_VARS = (
    "OPENAI_API_KEY", "VOYAGE_API_KEY", "PINECONE_API_KEY", "LANGFUSE_SECRET_KEY",
    "API_KEYS", "CLOUDINARY_URL", "CLOUDINARY_API_SECRET", "SENTRY_DSN",
)
EXPECTED_TAGS = ("app:instructor-assistant", "role:instructor", "feature:chat", "workflow:classic")
EXPECTED_META = (
    "role", "index_name", "sources_core", "sources_linked", "cited_slugs",
    "login_links", "rerank_empty", "app_version",
)


class LangfuseReader:
    """Read-only queries against the supported Langfuse read APIs."""

    def __init__(self) -> None:
        self.host = (os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
        self.auth = (os.getenv("LANGFUSE_PUBLIC_KEY") or "", os.getenv("LANGFUSE_SECRET_KEY") or "")

    def _window(self) -> tuple[str, str]:
        now = dt.datetime.now(dt.timezone.utc)
        return (now - dt.timedelta(hours=2)).isoformat(), (now + dt.timedelta(minutes=5)).isoformat()

    def ok(self) -> bool:
        r = requests.get(f"{self.host}/api/public/projects", auth=self.auth, timeout=30)
        return r.status_code == 200

    def observations(self, trace_id: str) -> list[dict]:
        start, end = self._window()
        r = requests.get(
            f"{self.host}/api/public/v2/observations", auth=self.auth, timeout=30,
            params={"traceId": trace_id, "fromStartTime": start, "toStartTime": end,
                    "fields": "core,basic,time,io,metadata,model,usage"},
        )
        r.raise_for_status()
        return r.json().get("data") or []

    def trace_tags_and_name(self, trace_id: str, column: str = "traceId") -> tuple[set[str], set[str]]:
        start, end = self._window()
        query = {
            "view": "observations",
            "dimensions": [{"field": "tags"}, {"field": "traceName"}],
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "filters": [{"column": column, "operator": "=", "value": trace_id, "type": "string"}],
            "fromTimestamp": start.replace("+00:00", "Z"), "toTimestamp": end.replace("+00:00", "Z"),
        }
        r = requests.get(f"{self.host}/api/public/v2/metrics", params={"query": json.dumps(query)},
                         auth=self.auth, timeout=30)
        r.raise_for_status()
        tags: set[str] = set()
        names: set[str] = set()
        for row in r.json().get("data") or []:
            tags.update(row.get("tags") or [])
            if row.get("traceName"):
                names.add(row["traceName"])
        return tags, names

    def scores(self, trace_id: str) -> list[dict]:
        r = requests.get(f"{self.host}/api/public/v3/scores", auth=self.auth, timeout=30,
                         params={"traceId": trace_id, "fields": "core,details"})
        r.raise_for_status()
        return r.json().get("data") or []

    def wait_for(self, trace_id: str, tries: int = 24) -> list[dict]:
        """Observations of a finished trace: the root has output and a rag-llm exists."""
        obs: list[dict] = []
        for _ in range(tries):
            try:
                obs = self.observations(trace_id)
                root = next((o for o in obs if not o.get("parentObservationId")), None)
                if root and root.get("output") is not None and any(o.get("name") == "rag-llm" for o in obs):
                    return obs
            except requests.RequestException:
                pass
            time.sleep(5)
        return obs


class Run:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.failures = 0
        self.lf = LangfuseReader()
        self.session = ""

    def result(self, name: str, problems: list[str], note: str = "") -> None:
        print(f"{'PASS' if not problems else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
        for p in problems:
            print(f"      - {p}")
        self.failures += bool(problems)

    def ask(self, question: str, session_prefix: str) -> str | None:
        headers = api_contract.client_headers(session_prefix)
        body = {"messages": [{"role": "user", "content": question}]}
        with requests.post(f"{self.url}/api/v1/chat", json=body, headers=headers, stream=True, timeout=240) as r:
            r.raise_for_status()
            _, annotations, _ = api_contract.parse_lines(r.iter_lines(decode_unicode=True))
        self.session = headers["X-Session-ID"]
        return next((a.get("trace_id") for a in annotations if a.get("trace_id")), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default=os.getenv("CHAT_API_URL", "http://localhost:8000"))
    parser.add_argument("--log", help="the server's log file, to scan for secrets")
    args = parser.parse_args()

    run = Run(args.url)
    if not run.lf.ok():
        print("FAIL  Langfuse rejected the credentials in .env; nothing to check")
        return 1

    # One normal question, a thumbs-down on it, an eval-session question, and
    # a question carrying an email and a student ID.
    trace_id = run.ask(QUESTION, "tracecheck")
    if not trace_id:
        run.result("1. chat trace", ["the stream carried no trace_id (is tracing on?)"])
        return 1
    requests.post(f"{run.url}/api/v1/chat/thumbs_request", headers=api_contract.client_headers("tracecheck"),
                  json={"trace_id": trace_id, "value": "bad", "comment": f"wrong for student {THUMBS_COMMENT_ID}"},
                  timeout=30).raise_for_status()
    eval_trace_id = run.ask(QUESTION, "eval-tracecheck")
    eval_run = run.session[len("eval-"):]
    pii_trace_id = run.ask(PII_QUESTION, "tracecheck")
    draft_headers = api_contract.client_headers("tracecheck-draft")
    requests.post(f"{run.url}/api/v1/chat/draft/edit", headers=draft_headers, timeout=120, json={
        "draft_type": "message", "instruction": "Make it warmer.", "selected_text": "Hello class.",
        "full_content": "Hello class. Welcome to the block.",
    }).raise_for_status()

    obs = run.lf.wait_for(trace_id)
    tags, names = run.lf.trace_tags_and_name(trace_id)
    index_tag = f"index:{os.getenv('PINECONE_INDEX_NAME', '')}"
    missing = [t for t in (*EXPECTED_TAGS, index_tag) if t not in tags]
    missing += [f"{p}*" for p in ("language:", "security:") if not any(t.startswith(p) for t in tags)]
    run.result("1. trace `chat` with the §9.1 tags",
               ([] if names == {"chat"} else [f"trace name(s) {sorted(names)}"]) + [f"missing tag {t}" for t in missing],
               f"trace {trace_id}, {len(obs)} observations")

    root = next((o for o in obs if not o.get("parentObservationId")), {})
    meta = root.get("metadata") or {}
    run.result("2. §9.1 metadata on the root", [f"missing metadata {k}" for k in EXPECTED_META if k not in meta],
               f"sources_core={meta.get('sources_core')}, cited={meta.get('cited_slugs')}")

    by_id = {o.get("id"): o for o in obs}
    orch = [o for o in obs if o.get("name") == "retrieval-orchestrator" and o.get("parentObservationId") == root.get("id")]
    rag = [o for o in obs if o.get("name") == "rag-llm" and by_id.get(o.get("parentObservationId"), {}).get("name") == "retrieval-orchestrator"]
    run.result("3. orchestrator under the root, rag-llm under the orchestrator",
               ([] if orch else ["no retrieval-orchestrator under the root"]) + ([] if rag else ["no rag-llm under the orchestrator"]),
               f"rag-llm model={rag[0].get('model') if rag else None}")

    scores = []
    for _ in range(12):
        scores = [s for s in run.lf.scores(trace_id) if s.get("name") == "user_feedback"]
        if scores:
            break
        time.sleep(5)
    problems = [] if scores else ["no user_feedback score"]
    if scores and THUMBS_COMMENT_ID in str(scores[0].get("comment")):
        problems.append("the thumbs comment reached Langfuse unredacted")
    run.result("4. thumbs score on the trace, comment redacted", problems,
               f"value={scores[0].get('value') if scores else None}, comment={scores[0].get('comment') if scores else None!r}")

    eval_tags, _ = run.lf.trace_tags_and_name(eval_trace_id) if eval_trace_id else (set(), set())
    if eval_trace_id and not eval_tags:
        run.lf.wait_for(eval_trace_id)
        eval_tags, _ = run.lf.trace_tags_and_name(eval_trace_id)
    run.result("5. eval traffic tagged",
               [f"missing {t}" for t in ("eval", f"eval_run:{eval_run}") if t not in eval_tags])

    pii_obs = run.lf.wait_for(pii_trace_id) if pii_trace_id else []
    dumped = json.dumps(pii_obs, default=str)
    pii_root = next((o for o in pii_obs if not o.get("parentObservationId")), {})
    pii_rag = next((o for o in pii_obs if o.get("name") == "rag-llm"), {})
    problems = [f"{label} reached Langfuse unmasked" for label, value in (("email", PII_EMAIL), ("student ID", PII_ID)) if value in dumped]
    for label, o in (("root input", pii_root), ("rag-llm prompt", pii_rag)):
        text = str(o.get("input") or "")
        if not ("[email]" in text and "[number]" in text):
            problems.append(f"{label} doesn't show [email]/[number]")
    run.result("6. identifiers masked in Langfuse", ([] if pii_obs else ["trace never appeared"]) + problems)

    haystacks = {"Langfuse observations": json.dumps(obs, default=str) + dumped}
    if args.log and Path(args.log).exists():
        haystacks["server log"] = Path(args.log).read_text(encoding="utf-8", errors="replace")
    secrets = [(var, value.strip()) for var in SECRET_VARS
               for value in (os.getenv(var) or "").split(",") if len(value.strip()) >= 8]
    problems = [f"{var} appears in the {where}" for where, text in haystacks.items()
                for var, value in secrets if value in text]
    run.result("7. no secrets in traces or logs", problems,
               f"{len(secrets)} secret values checked against {', '.join(haystacks)}")

    draft_tags: set[str] = set()
    for _ in range(12):
        draft_tags, _names = run.lf.trace_tags_and_name(draft_headers["X-Session-ID"], column="sessionId")
        if any(t.startswith("outcome:") for t in draft_tags):
            break
        time.sleep(5)
    outcome = sorted(t for t in draft_tags if t.startswith("outcome:"))
    run.result("8. late tags reach the trace (draft edit outcome:*)",
               [] if outcome else [f"no outcome:* tag (tags seen: {sorted(draft_tags)})"], ", ".join(outcome))

    print(f"\n{'ALL PASSED' if not run.failures else f'{run.failures} FAILED'}")
    return 1 if run.failures else 0


if __name__ == "__main__":
    sys.exit(main())
