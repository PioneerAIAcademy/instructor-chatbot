# Instructor Assistant: frontend

The web app for the BYU-Pathway Instructor Assistant (CLAUDE.md §7 Phase 8). A Next.js 15
static export, copied from pathway-chatbot `870cc5b` and trimmed: no ACM mode, calendar,
tuition, dictation, uploads, or LlamaCloud. It talks only to the backend's documented API
([`../backend/API.md`](../backend/API.md)).

Design: **the Missionary Assistant's design, in blue** (owner's decision, 2026-10-20).
The layout and components are upstream's. Two things change: the brand color, from
gold `#FFC328` to blue, and the answer format, which follows the owner's prototype (below).
The font is **Mulish** across the app (owner, 2026-10-20); the greeting keeps Georgia.

The blue is **`#056CB6`** (owner's choice), with navy `#0F4B8F` for hover.

| Missionary (gold) | Instructor (blue) |
| --- | --- |
| Header bar `#FFC328`, gray logo and title | `#056CB6`; the logo, title, and gear show in white (gray would be unreadable on it; the logo file is unchanged) |
| Gold buttons (send, stop, submit, send feedback, save) | `#056CB6` with white, hover `#0F4B8F` |
| Gold tints (selected items, hovers, selection, highlights) | Light tints of `#056CB6` |
| Amber focus ring | `#056CB6` |
| The gold path mark (bot avatar, favicon, home-screen icons) | The same mark in `#056CB6` (`public/BYU-pathway-icon-logo-blue.png`, `favicon.ico`, `apple-touch-icon.png`, `android-chrome-*.png`) |

Dark-mode link text and one field border use a lighter blue (`#8EBDDE`): `#056CB6` text
on the dark page is about 3.3:1, under the 4.5:1 text needs.

Opening screen: for 1 s on every visit (upstream's loader held 800 ms), the name
**INSTRUCTOR ASSISTANT** shows in light gray while a `#056CB6` band sweeps through it to
the right and back to the left, and keeps sweeping until the app is ready (owner,
2026-10-20). The screen is in the page's HTML, so on a slow connection it shows, still
moving, until the app has loaded. With reduced motion it is simply blue.

Answers, as in the owner's prototype screenshot:
- Mulish 16px text in gray `#454540` (`#D6D6D6` dark), line height 1.6.
- Citations are round numbered badges: light blue `#8EBDDE` with a gray number,
  `#056CB6` with white on hover or keyboard focus. Hovering one previews the source; up
  to 3 at one spot show side by side, more collapse to the first plus "+N".
- Highlights (`mark`) and dates are pale blue `#E7F0FA`, rounded 8px.
- Links are navy `#0F4B8F`, underlined. A sign-in link gets a lock icon, and the
  backend's "(sign-in required)" note shows small and gray.
- Under the answer, one row: an outlined **Sources (N)** pill with a book icon, then
  round outlined thumbs up, thumbs down, copy, and regenerate (44px on phones, 40px
  up). The suggested follow-ups below it are pale-blue pills.

Differences from upstream on purpose:
- Citation pills show a local document or globe icon, not the site's favicon from Google
  (which sent Google every cited domain).
- The Sources pill and drawer list only the cited sources, labeled "Instructor guide
  (PDF)" or "External page · host".
- Starter questions show on the empty chat (upstream fetched but never showed them).
- The "PRIVACY:" notice sits where upstream's "IMPORTANT:" note was, and stays.

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
  **Sources (N)** opens a panel listing each cited source, numbered like its badge, as
  "Instructor guide (PDF)" or "External page · host", with a link to it. Sign-in links
  show a lock and carry "(sign-in required)", added by the backend.
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
