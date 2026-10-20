# Deploying the backend (staging and production)

How to run the Instructor Assistant backend on a host (CLAUDE.md §7 Phase 7). It is one
Docker service. It needs no disk, no database, and no inbound access besides HTTP.

## 1. Build the image

```bash
cd backend
docker build --build-arg APP_VERSION=$(git rev-parse --short HEAD) -t instructor-backend .
```

- `.dockerignore` is an allow-list: the image gets `main.py`, `app/`, `pyproject.toml`, and
  `poetry.lock`, nothing else. A local `.env` never goes into the image.
- `APP_VERSION` (the git commit) shows up in Langfuse traces and Sentry releases.
- The container runs as a non-root user (uid 10001) and defaults to `ENVIRONMENT=prod`.
- CI (`.github/workflows/test.yml`, job "backend (docker image)") builds this image on
  every push and checks all of the above, plus the boot guard, the API key, and CORS.

Most hosts can build straight from the repo instead: point them at `backend/Dockerfile` with
`backend/` as the build context.

## 2. Settings on the host

Set these as the host's environment variables (or secrets). Names only here; values come
from the owner. Never commit them, and never bake them into the image.

**Required**

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI key (answers and query embeddings) |
| `VOYAGE_API_KEY` | Voyage key (reranking). The server won't start without it. |
| `PINECONE_API_KEY` | A key from the **instructor** Pinecone account. Never the missionary bot's. |
| `PINECONE_INDEX_NAME` | `instructor-assistant` |
| `PINECONE_ENVIRONMENT` | `us-east-1` |
| `MODEL_PROVIDER`, `MODEL` | `openai`, `gpt-4o-mini` |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM` | `text-embedding-3-large`, `3072` (must match the index) |
| `API_KEYS` | The key the frontend sends as `X-API-Key`. If it is empty, every chat request is refused with 503; a missing or wrong key gets 401. |
| `ALLOWED_ORIGINS` | The frontend's URL, comma-separated if several. Empty until the frontend exists (Phase 8). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | The instructor Langfuse project |

**Recommended**

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `staging` or `prod` (the image defaults to `prod`). Never `dev` on a host: `dev` shows error details, and with `API_KEYS` empty it lets every request in. |
| `CONVERSATION_STARTERS` | The 4 starter questions, separated by `\n` (see `.env.example`) |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT` | The instructor Sentry project. Keep `SENTRY_SEND_PII` unset (false). |

**Never set on a host:** `CORS_ALLOW_ALL=true`, and `PINECONE_INDEX_NAME=pathway` (the boot
guard refuses it anyway).

`PORT`: the server listens on `$PORT` if the host sets it, and on 8000 otherwise.

## 3. Health checks

- Liveness: `GET /api/health` returns `{"status": "ok"}` and calls nothing external. Use this
  as the host's health check.
- Readiness: `GET /api/health/ready` returns `{"status", "index", "guard"}`. It reads Pinecone
  and Langfuse, so poll it by hand after a deploy, not every few seconds.

## 4. After each deploy (the Phase 7 "Backend done" gate)

Run these from a laptop, with `API_KEYS` set to the deployed key in your shell:

```bash
cd backend
URL=https://<your-backend-host>

curl -s $URL/api/health/ready                     # expect index=instructor-assistant, guard=ok
CHAT_API_URL=$URL poetry run python scripts/api_check.py      # the API contract and G4
poetry run python scripts/eval_answers.py --url $URL          # answers >= 85%, guards 4/4
```

Then confirm:

- A chat request without `X-API-Key` gets 401.
- Traces land in the **instructor** Langfuse project, tagged `app:instructor-assistant`.
- The missionary bot's deployment and settings are unchanged.

Record the eval result file name in CLAUDE.md §14.
