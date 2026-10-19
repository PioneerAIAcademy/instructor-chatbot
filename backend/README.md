# Instructor Assistant — backend

The FastAPI backend for the **BYU-Pathway Instructor Assistant**. It answers questions from
BYU-Pathway online instructors, using only the Pinecone index `instructor-assistant`, which the
[`instructor-indexer`](https://github.com/PioneerAIAcademy/instructor-indexer) repo builds.
It is a trimmed copy of the
[Missionary Assistant backend](https://github.com/PioneerAIAcademy/pathway-chatbot).

[`../CLAUDE.md`](../CLAUDE.md) holds the full plan, the repo rules, and the journal.
[`../UPSTREAM.md`](../UPSTREAM.md) lists which files came from upstream and what changed.

> **Status:** Phase 1 (audience lock and index switch) of the build plan in `CLAUDE.md` §7.
> The chat path works end to end with all three audience guards. The sign-in link labels and
> the evals arrive in later phases.

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
| `VOYAGE_API_KEY` | The reranker. **Required at startup**: the Voyage client is created on import. |
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

The response is a stream of lines:

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
| GET | `/api/health/ready` | none | — | Readiness: checks the index guard, Pinecone, and Langfuse. Returns `status`, `index`, `guard`. |

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

To see what retrieval returns for one question, through the same guard, filter, and rerank as
`/api/v1/chat` (live and billable; no LLM answer is generated):

```bash
poetry run python scripts/retrieve.py "When do instructors in the US get paid?"
poetry run python scripts/retrieve.py "..." --expect pay-dates-for-worldwide-online-instructors-ia
```

With `--expect`, it exits 1 unless that slug ranks in the top 5 after rerank.

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
  engine/prompts.py             system, context, and condense prompts
  engine/retrieval_orchestrator.py  engine, then grounding guards
  engine/custom_condense_plus_context.py  retrieval, rerank, context building
  engine/grounding_guard.py     citation coverage, link integrity
  engine/vectordb.py            bounded, cached Pinecone client
  security/input_validator.py   input security screen
tests/                          offline tests
scripts/retrieve.py             raw + reranked retrieval for one question (live)
scripts/                        security corpus and harness
```

## Index guard

The server refuses to start (`IndexConfigError`) unless:

- `PINECONE_INDEX_NAME` is in `ALLOWED_INDEX_NAMES` (default `instructor-assistant`);
- it isn't `pathway`, the Missionary Assistant's index. That name is refused even if someone
  adds it to the allow-list;
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
