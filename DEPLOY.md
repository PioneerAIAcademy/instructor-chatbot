# Deploying the Instructor Assistant

Two Docker services, each with its own URL (CLAUDE.md §13 Q3): the **backend** (FastAPI,
Phase 7) and the **frontend** (a static site, Phase 8). Neither needs a disk or a database.
Deploy the backend first: the frontend is built with the backend's URL baked in, and the
backend only accepts the frontend's origin.

1. Backend: build, settings, health, post-deploy checks (Phase 7, "Backend done").
2. Frontend: build, settings, post-deploy checks.
3. Going live (Phase 9): the end-to-end checks against production.

# Part 1: backend

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
| `ALLOWED_ORIGINS` | The frontend's URL, comma-separated if several (Part 2). Until the frontend has a URL, leave it empty: browsers are then refused, and scripts still work. |
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

**The prompt-injection detector** (`PROMPT_INJECTION_ML_ENABLED`, on by default) shapes
the instance size:
- It downloads a 714 MB model from Hugging Face at startup (in the background; questions
  are answered meanwhile, with the regex checks only).
- Each server process holds its own copy, about 0.5 GB of RAM. The image runs 2 gunicorn
  workers, so allow about 1 GB for the detector alone.

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

# Part 2: frontend

## 5. Build the image

The `NEXT_PUBLIC_*` values are compiled into the site at build time, so they are build
arguments. A change to any of them means a rebuild, not a restart.

```bash
cd frontend
docker build \
  --build-arg NEXT_PUBLIC_CHAT_API=https://<backend-host> \
  --build-arg NEXT_PUBLIC_API_KEY=<one of the backend's API_KEYS> \
  --build-arg NEXT_PUBLIC_SITE_URL=https://<frontend-host> \
  -t instructor-frontend .
```

- `.dockerignore` is an allow-list, so no `.env*` file reaches the build. The image holds
  only the built site (`out/`) and a pinned static server, and runs as the `node` user.
- It listens on `$PORT` if the host sets one, and on 3000 otherwise.
- `public/serve.json` sets the security headers: a Content Security Policy, frame blocking,
  `nosniff`, and a referrer policy.
- CI (job "frontend (build, tsc, lint)") builds this image on every push and checks a
  planted `.env.local` doesn't ship.
- Static hosting works too: run `npm run build` with the same variables and serve `out/`.
  Copy the headers from `public/serve.json` into the host's settings.

**Settings** (build arguments; see `frontend/.env.example`):

| Variable | Needed | Value |
| --- | --- | --- |
| `NEXT_PUBLIC_CHAT_API` | yes | The backend's URL |
| `NEXT_PUBLIC_API_KEY` | yes | One of the backend's `API_KEYS`. It ships in the page, so it's a speed bump, not a secret. |
| `NEXT_PUBLIC_SITE_URL` | recommended | This site's URL (social previews) |
| `NEXT_PUBLIC_HELP_URL` | no | The instructor help page; the Settings "Help" item stays hidden until set |
| `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | no | The instructor Sentry project |

The API key needs no extra handling in the build: it's visible to anyone who opens the
site.

## 6. Point the backend at the frontend

On the backend, set `ALLOWED_ORIGINS=https://<frontend-host>` (only that one), keep
`CORS_ALLOW_ALL` unset, and restart it. Then check that CORS answers only that origin:

```bash
B=https://<backend-host>
curl -s -o /dev/null -D - -X OPTIONS $B/api/v1/chat \
  -H 'Origin: https://<frontend-host>' -H 'Access-Control-Request-Method: POST' \
  | grep -i access-control-allow-origin          # expect: the frontend's origin
curl -s -o /dev/null -D - -X OPTIONS $B/api/v1/chat \
  -H 'Origin: https://example.com' -H 'Access-Control-Request-Method: POST' \
  | grep -i access-control-allow-origin          # expect: nothing
```

# Part 3: going live (Phase 9)

Run these against **production** once both services are up. All are live and billable.

```bash
cd backend                    # API_KEYS set to the deployed key in your shell
poetry run python scripts/api_check.py --url https://<backend-host>     # API contract, G4
poetry run python scripts/eval_answers.py --url https://<backend-host>  # answers >= 85%, guards 4/4

cd ../frontend                # the site itself, in headless Chrome
node scripts/e2e_check.mjs --url https://<frontend-host> --out e2e-shots
```

`scripts/e2e_check.mjs` asks 5 §10 questions (#1, #5, #9, #21, G3) through the real
page and checks:
- the empty chat shows starters and the FERPA notice;
- each answer has citation badges, and "Sources (N)" matches them;
- every source card says "Instructor guide (PDF)" or "External page · host";
- every sign-in link says "(sign-in required)";
- no missionary wording appears;
- a thumbs click is answered 200.

It saves a screenshot per question; look through them as the "manual run" of Phase 9.

Phase 9 is done when:
- the answer eval passes against production;
- `e2e_check.mjs` passes against the production site;
- the CORS check in step 6 refuses another origin;
- the missionary deployment and its settings are unchanged.

Record the eval result file and the date in CLAUDE.md §14.
