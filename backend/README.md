# Instructor Assistant — backend

The FastAPI backend for the **BYU-Pathway Instructor Assistant**. It answers questions from
BYU-Pathway online instructors, using only the Pinecone index `instructor-assistant`, which the
[`instructor-indexer`](https://github.com/PioneerAIAcademy/instructor-indexer) repo builds.
It is a trimmed copy of the
[Missionary Assistant backend](https://github.com/PioneerAIAcademy/pathway-chatbot).

[`../CLAUDE.md`](../CLAUDE.md) holds the full plan, the repo rules, and the journal.
[`../UPSTREAM.md`](../UPSTREAM.md) lists which files came from upstream and what changed.

> **Status:** Phase 4 (chat API) of the build plan in `CLAUDE.md` §7. The API is fixed and
> documented in [`API.md`](API.md), the contract the frontend builds against. The answer eval
> arrives in Phase 6.

## How a question is answered

1. `POST /api/v1/chat` checks the API key and the rate limit, then runs the input security screen.
2. Retrieval is filtered to `role == "instructor"` and `source in RETRIEVAL_SOURCES`. This filter
   is fixed on the server. Any `role` the client sends is ignored. A second check after
   retrieval drops any chunk with the wrong role or source and logs `audience_leak`. It should
   never fire.
3. Pinecone returns the top 35 chunks. Voyage `rerank-lite-1` keeps the top 17 with a score of at
   least 0.21. Chunks are then grouped by document and put back in page order.
4. OpenAI writes the answer from those chunks, with `[^N]` citations.
5. Deterministic guards add a citation to any uncited claim line in an answer that has
   citations. They leave drafts in ```` ```message ```` or ```` ```email ```` blocks free of citations, and strip
   any link that doesn't appear in a source. If the answer fails, the stream sends a short
   "service hiccup" message instead of an empty reply.
6. Links to pages that need a BYU-Pathway or BYU-Idaho sign-in (hosts in `LOGIN_LINK_HOSTS`:
   SharePoint and OneDrive, the course directory, Companion, the portal) get the sign-in note,
   "(sign-in required)", in the answer's language, once. The model is told not to write the
   note itself, so the label is always the localized one. Links inside a drafted message are
   left alone. The bot never opens those pages; the prompt forbids describing them.
6. The answer streams back in the Vercel AI SDK data-stream format, followed by the sources and
   suggested follow-up questions. The request is traced in Langfuse.

## Setup

You need Python 3.12 and [Poetry](https://python-poetry.org/) 1.8 or newer.

```bash
bash ../scripts/setup-dev.sh   # once per clone: activates the git hooks
poetry install
cp .env.example .env           # then fill in values; .env is gitignored
```

`.env.example` lists every variable by name. `CLAUDE.md` §11 explains each one. To answer
questions you need at least:

| Variable | Notes |
| --- | --- |
| `OPENAI_API_KEY` | The LLM and query embeddings. |
| `VOYAGE_API_KEY` | The reranker. **Required at startup**: `main.py` refuses to boot without it. (The client itself is created on first use, so scripts and tests can import the app without it.) |
| `PINECONE_API_KEY` | A key from the **instructor** Pinecone account. Never the missionary bot's key. |
| `PINECONE_INDEX_NAME` | `instructor-assistant` |
| `PINECONE_ENVIRONMENT` | `us-east-1` |
| `MODEL_PROVIDER`, `MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` | `openai`, `gpt-4o-mini`, `text-embedding-3-large`, `3072`. The embedding model must match the index. |
| `ENVIRONMENT` | `dev` locally. Anything else hides error details and switches to JSON logs. |

Langfuse (`LANGFUSE_*`) and Sentry (`SENTRY_DSN`) are optional locally. If they aren't set,
tracing is turned off and the server says so in its startup logs.

## Run

```bash
poetry run python main.py      # http://localhost:8000, auto-reload in dev
```

Interactive API docs: <http://localhost:8000/api/docs>

Ask a question:

```bash
curl -N localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"When do instructors in the US get paid?"}]}'
```

[`API.md`](API.md) is the full contract: request body and headers, every annotation, error
shapes, and the other routes. The response is a stream of lines:

- `0:"..."` is answer text. A failed answer arrives as a short localized "service hiccup"
  message, with no `sources`.
- `8:[{...}]` is an annotation: `events`, `date_spans`, `user_language`, `sources`, or
  `suggested_questions`.

Each line is followed by newline padding, so the stream flushes without delay. Phase 4 writes
the full contract to `API.md`.

## Endpoints

| Method | Path | Auth | Rate limit | Purpose |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/chat` | API key | 10/min | Streaming chat |
| POST | `/api/v1/chat/draft/edit` | API key | 20/min | Rewrite selected text in a drafted message |
| POST | `/api/v1/chat/thumbs_request` | API key | 30/min | Thumbs up/down, saved as a Langfuse score on the trace |
| POST | `/api/v1/chat/feedback/general` | API key | 5/min | General feedback, with an optional screenshot (Cloudinary) |
| GET | `/api/v1/chat/config` | none | — | Starter questions, from `CONVERSATION_STARTERS` |
| GET | `/api/health` | none | — | Liveness |
| GET | `/api/health/ready` | none | — | Readiness: checks the index guard, Pinecone (a data-plane call through the same client chat uses), and Langfuse. Returns `status`, `index`, `guard`. |

Rate limits are per client IP. Requests send the API key in an `X-API-Key` header, checked
against `API_KEYS` (comma-separated). The key is skipped only when `ENVIRONMENT=dev` **and**
`API_KEYS` is empty. Anywhere else, an empty `API_KEYS` rejects every request. The key ships in
the frontend bundle, so it slows abuse down but doesn't control access.

`messages` may only use the roles `user` and `assistant`, and the last one must be `user`.
Anything else gets a 422.

Optional headers: `X-Session-ID` (the Langfuse session), `X-Device-ID` (the Langfuse user),
and `X-Timezone` (sets "today's date" in the prompt).

## Tests

```bash
poetry run pytest tests/ -q
```

The tests run offline and need no keys. CI (`.github/workflows/test.yml`) runs them that way,
and the `pre-push` hook moves `.env` aside first, so it matches CI.

Tests that call OpenAI, Voyage, or Pinecone cost money. They run only when `RUN_LIVE_TESTS=1`
is set.

To check the whole API against a running server (the Phase 4 done-when: the stream contract,
document URLs, citations, the ignored client role, thumbs, draft edit, feedback, routes,
starters; live and billable):

```bash
poetry run python scripts/api_check.py                  # default http://localhost:8000
```

`scripts/api_contract.py` is the stream contract as code. `tests/test_api_contract.py` checks
it offline against the real app; `api_check.py` checks it live.

To ask one question through the running local API and check the answer (live and billable; a
real chat request):

```bash
poetry run python main.py                                  # in another terminal
poetry run python scripts/ask.py "How do I find my ACL?"
```

It prints the answer, its sources, and the trace ID, then checks that every sign-in link carries
the note, that there are no reading claims ("I read/opened/checked/reviewed"), that every `[^N]`
maps to a source, and that every source is `role=instructor`. It exits 1 if a check fails.

To see what retrieval returns for one question, through the same guard, filter, and rerank as
`/api/v1/chat` (live and billable; no LLM answer is generated):

```bash
poetry run python scripts/retrieve.py "When do instructors in the US get paid?"
poetry run python scripts/retrieve.py "..." --expect pay-dates-for-worldwide-online-instructors-ia
```

With `--expect`, it exits 1 unless that slug ranks in the top 5 after rerank.

To run the retrieval eval, which sends the 21 non-guard questions in `tests/eval/questions.yaml`
through the production retriever and rerank (live and billable; no LLM answers):

```bash
poetry run python scripts/eval_retrieval.py            # all 21
poetry run python scripts/eval_retrieval.py --ids 4 21 # a few
```

A question hits when an expected document is in the top 5 chunks after rerank, the same rule
as the indexer's `verify`. The run passes at hit@5 ≥ 90% with no empty contexts, no
non-instructor nodes, no failed reranks (a failed rerank falls back to raw order, so the rerank
wasn't measured), and no errors. A question that errors is recorded and the run carries on. For
each miss, it says why: pushed out of the raw top 5 by rerank, retrieved lower and not lifted,
not retrieved, rerank failed, or an error.

To run the answer eval, which sends all 25 questions through the running chat API and checks
each answer (live and billable: a full chat request per question):

```bash
poetry run python scripts/eval_answers.py                  # all 25
poetry run python scripts/eval_answers.py --ids 5 G4       # a few (G4 brings #5 along)
poetry run python scripts/eval_answers.py --rescore tests/eval/results/<run>-answers.json  # free
RUN_LLM_JUDGE=1 poetry run python scripts/eval_answers.py  # adds a groundedness judge
```

Each answer is checked for: the expected guide cited, every `[^N]` matching a source, only
instructor sources, the required phrases, no forbidden phrases, a sign-in label on every
sign-in link, refusals where expected, a ```message fence for the draft question, and (G4) the
same sources whatever role the client sends. The run passes when at least 85% of the 21 answer
questions and all 4 guards pass. Requests use the session `eval-<run>`, so their traces are
tagged `eval` and get an `eval_pass` score. `--rescore` re-checks a saved run against the
current `questions.yaml` without sending anything.

Phrases in `questions.yaml` (`must_include`, `must_not`) match whole words, case-insensitively:
`ACM` doesn't match "Macmillan" and `ID` doesn't match "guide". A trailing `*` makes a prefix
(`missionar*`).
Results go to `tests/eval/results/<timestamp>-retrieval.json` (gitignored).

To re-run the security attack corpus after any change to
`app/security/input_validator.py`:

```bash
poetry run python scripts/sec_test.py
```

## Layout

```
main.py                         app, CORS, body-size limit, routers
app/
  api/routers/chat.py           chat, draft edit, thumbs, feedback
  api/routers/vercel_response.py  the SSE stream
  api/services/                 suggested questions, draft rewrite
  engine/audience_guard.py      index guard, instructor filter, post-retrieval role check
  engine/prompts.py             system, context, and condense prompts (locked by tests/test_prompts_lock.py)
  engine/login_links.py         "(sign-in required)" labels on sign-in links
  engine/retrieval_orchestrator.py  engine, then grounding guards
  engine/custom_condense_plus_context.py  retrieval, rerank, context building
  engine/grounding_guard.py     citation coverage, link integrity
  engine/vectordb.py            bounded, cached Pinecone client
  security/input_validator.py   input security screen
tests/                          offline tests
API.md                          the API contract (request, stream, errors, routes)
scripts/api_check.py            Phase 4 live API check against a running server
scripts/api_contract.py         the stream contract as code (shared by tests and api_check)
scripts/ask.py                  one question through the local API, with answer checks (live)
scripts/retrieve.py             raw + reranked retrieval for one question (live)
scripts/eval_retrieval.py       retrieval eval over tests/eval/questions.yaml (live)
scripts/eval_answers.py         answer eval through the chat API (live; --rescore is free)
scripts/evalset.py              eval-set loader and scoring (shared with the Phase 6 answer eval)
tests/eval/questions.yaml       the §10 eval set (DRAFT until real instructor questions arrive)
scripts/                        security corpus and harness
```

## Tracing and privacy

Every request is traced in Langfuse (keys in `.env`, a separate project for this app). A
`chat` trace carries these tags:
- `app:instructor-assistant`, `role:instructor`, `index:<name>`;
- `feature:chat`, `workflow:classic`;
- `language:<xx>`, `security:<clean|risk_*>`;
- `eval` and `eval_run:<id>` when `X-Session-ID` starts with `eval-`.

Its metadata records which sources the answer used and cited, the sign-in link counts, and
`app_version` (`APP_VERSION`). LLM calls appear under it as `rag-llm` generations, and thumbs
add a `user_feedback` score.

Instructors may type student details into questions, so before anything is sent to Langfuse,
emails and runs of 7 or more digits (student IDs, phone numbers) are masked in every
observation's input, output, and metadata, including the `rag-llm` prompts (`app/redaction.py`).
URLs and dates are left alone. Names can't be masked by pattern, so metadata never carries the
question. Logs contain no question text. Sentry gets no request bodies or stack locals, and its
exception messages, log entries, and breadcrumbs are redacted.

The SDK is langfuse 4.x (OpenTelemetry-based). The 2.x ingestion API is shut down on Langfuse
Cloud on 2026-11-16, and new organizations can't read its data. `app/api/tracing.py`'s
`RequestTrace` holds a request's trace open while the answer streams. To read traces in a new
Langfuse organization, use `GET /api/public/v2/observations`, `/api/public/v2/metrics` (tags),
and `/api/public/v3/scores`; the older read endpoints return 410. Tests never send anything to
Langfuse: `tests/conftest.py` turns tracing off.

To check all of this against a running server (live; reads traces back from Langfuse):

```bash
poetry run python main.py > server.log 2>&1      # in another terminal
poetry run python scripts/trace_check.py --log server.log
```

## Index guard

The server refuses to start (`IndexConfigError`) unless:

- `PINECONE_INDEX_NAME` is in `ALLOWED_INDEX_NAMES` (default `instructor-assistant`);
- it isn't `pathway`, the Missionary Assistant's index, or a copy named after it
  (`pathway-…`, `pathway_…`, or anything containing "missionar"). These are refused even if
  someone adds them to the allow-list;
- `PINECONE_INDEX_HOST`, when set, is that same index's Pinecone host.

The vector store repeats the check, so scripts that skip `main.py` are covered too.

## Rules that matter here

- **Pinecone is read-only from this repo.** Only `instructor-indexer` writes to the index.
- **Never weaken the audience guards**, not even temporarily: the role and source filter,
  the index guard, the role check after retrieval, and the security screen. If a guard fires,
  report it as a finding; don't make a test pass by loosening it.
- **No secrets in committed files.** Values belong in `.env` only.
- **No AI or co-author attribution in commits.** The `commit-msg` hook blocks it.
- **Work on a branch and open a PR.** Never push to `main`.

## Deploy

`Dockerfile` builds a Python 3.12 image and runs gunicorn with 2 Uvicorn workers. Each worker
restarts after about 500 requests. In production, set `ENVIRONMENT=prod`, `API_KEYS`, and
`ALLOWED_ORIGINS` (the instructor frontend only), and keep `CORS_ALLOW_ALL=false`. Staging
and production come in Phases 7 and 9.
