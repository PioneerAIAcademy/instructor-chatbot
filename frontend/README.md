# Instructor Assistant: frontend

The web app for the BYU-Pathway Instructor Assistant (CLAUDE.md §7 Phase 8). A Next.js 15
static export, copied from pathway-chatbot `870cc5b` and trimmed: no ACM mode, calendar,
tuition, dictation, uploads, or LlamaCloud. It talks only to the backend's documented API
([`../backend/API.md`](../backend/API.md)).

Design: **direction D, "light chrome"** from the all-blue prototype. A white header with
the BYU-Pathway logo as-is, Blue 4 `#056CB6` for things you act on, Mulish for text and
Crimson Pro for the greeting and headings. The palette is defined once, as CSS variables
in `app/globals.css` and Tailwind colors `ia-*` in `tailwind.config.ts`; components use
those, not raw hex.

## Run it

```bash
cd frontend
npm ci
cp .env.example .env.local          # NEXT_PUBLIC_CHAT_API=http://localhost:8000
npm run dev                         # http://localhost:3000
```

The backend must allow this origin: start it with `ALLOWED_ORIGINS=http://localhost:3000`
(or set that in `backend/.env`). With `ENVIRONMENT=dev` and no `API_KEYS`, no key is needed.
Set `CONVERSATION_STARTERS` on the backend to see starter questions on the empty chat.

Checks (CI runs the same):

```bash
npm run build && npx tsc --noEmit && npm run lint
```

`npm run build` writes the static site to `out/`. It also creates `next-env.d.ts`, which
`tsc` needs, so build first.

End-to-end check (live, billable: 5 real questions through the page, in headless Chrome):

```bash
node scripts/e2e_check.mjs --url http://localhost:3000     # or the production URL
```

It checks starters and the FERPA notice, citation badges and the Sources count, the source
type labels, sign-in labels, no missionary wording, and that thumbs reach the backend. It
saves a screenshot per question in `e2e-shots/` (gitignored). Needs Node 22+ and Chrome
(`CHROME_PATH` if not at the macOS default).

## Settings (build time)

`NEXT_PUBLIC_*` values are compiled into the JavaScript and visible to anyone, so none of
them is a secret. See `.env.example`.

| Variable | Needed | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_CHAT_API` | yes | The backend's origin |
| `NEXT_PUBLIC_API_KEY` | in prod | Sent as `X-API-Key`; must be one of the backend's `API_KEYS` |
| `NEXT_PUBLIC_SITE_URL` | no | This site's URL, for social previews |
| `NEXT_PUBLIC_HELP_URL` | no | The instructor help page; the Settings "Help" item is hidden until set |
| `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | no | The Instructor Assistant's Sentry project |
| `SENTRY_ORG`, `SENTRY_PROJECT`, `SENTRY_AUTH_TOKEN` | no (CI) | Source map upload; never `NEXT_PUBLIC_` |
| `DEV_PROXY_BACKEND` | no (local) | Proxies `/api/*` to a backend when testing over a tunnel |

## What it uses from the backend

| Endpoint | Used for |
| --- | --- |
| `POST /api/v1/chat` | The answer stream (Vercel AI data stream). It handles only the annotations in `API.md`: `events`, `date_spans`, `user_language`, `sources`, `suggested_questions`. |
| `GET /api/v1/chat/config` | The starter questions on the empty chat |
| `POST /api/v1/chat/thumbs_request` | Thumbs up/down on an answer (a Langfuse score on its trace) |
| `POST /api/v1/chat/feedback/general` | Settings → Send feedback |
| `POST /api/v1/chat/draft/edit` | "Tweak" in the draft composer |

The request body carries the question, the language preference, and any edited draft. It
never carries a role: the backend serves one audience and ignores a client role.

## What instructors see

- **Empty chat:** a greeting, up to 4 starter questions, and a disclaimer.
- **Under the input, always:** "Don't include student names, IDs, or grades." (CLAUDE.md
  §9.2) and the AI note.
- **Answers:** numbered citation badges (`[^N]`). Hovering one previews the source.
  **Sources (N)** opens a panel listing each source as "Instructor guide (PDF)" or
  "External page · host", with a link to it. Sign-in links carry "(sign-in required)",
  added by the backend.
- **Drafts:** a ```` ```message ```` or ```` ```email ```` answer opens in the draft
  composer (edit, tweak, copy, open in Gmail/Outlook).

Apart from Sentry (when its DSN is set), the page makes no third-party requests. The
fonts come from pinned npm packages (`@fontsource-variable/*`) through `next/font/local`,
so neither a build nor a visit contacts Google, and the source favicons upstream fetched
from Google are gone.

## Deploy

[`../DEPLOY.md`](../DEPLOY.md) Part 2 covers both services together. In short: `Dockerfile` builds the static site and serves it with a pinned `serve` on `$PORT`
(default 3000). `public/serve.json` sets the security headers: CSP, `X-Frame-Options`,
`nosniff`, and a referrer policy. `.dockerignore` is an allow-list, so no `.env*` file
reaches the image. Pass the `NEXT_PUBLIC_*` values as build arguments:

```bash
docker build --build-arg NEXT_PUBLIC_CHAT_API=https://<backend> \
             --build-arg NEXT_PUBLIC_API_KEY=<key> -t instructor-frontend .
```

Then set the backend's `ALLOWED_ORIGINS` to this site's URL only (Phase 9).
