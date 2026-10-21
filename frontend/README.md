# Instructor Assistant: frontend

The web app for the BYU-Pathway Instructor Assistant (CLAUDE.md §7 Phase 8). A Next.js 15
static export, copied from pathway-chatbot `870cc5b` and trimmed: no ACM mode, calendar,
tuition, dictation, uploads, or LlamaCloud. It talks only to the backend's documented API
([`../backend/API.md`](../backend/API.md)).

Design: **BYU gold, in a layout of its own** (owner and the instructor team,
2026-10-20). The team wanted BYU gold, and an app that instructors can't mistake for the
Missionary Assistant (a gold bar across the top, one centered column, a serif greeting).
The layout follows a chat-UI mockup a staff member on the instructor team shared; the
font is **Mulish** throughout.

- **Top bar:** BYU gold `#FFC328` (in dark mode too), with the BYU-Pathway logo and
  "Instructor Assistant" on the left. On the right, **New chat** (in a chat: clears it
  and starts a new session) and the settings gear. Everything on the bar is near-black,
  including its focus ring; the logo's dark-gray artwork is about 6:1 on gold.
- **Welcome:** "Good morning. What can I help with?", a subtitle, and up to 4 cards in
  the middle, above the question box (owner). The backend serves 4 instructor cards by
  default; `CONVERSATION_STARTERS` overrides them, and a line `Title | question` is a
  card with that title that asks the question.
- **Answers:** a small gold avatar; gold numbered citation badges (hover previews the
  source); the cited guides as chips under the text (they open the sources panel); then
  small gray copy, thumbs, and regenerate icons; follow-ups as outlined pills.
- **Question box:** white with a soft border (gold when focused), a gold send button,
  a dark stop button. It stays at the bottom on every screen, the welcome screen
  included (owner). The privacy line and the note on where answers come from sit
  under it.
- **Opening screen:** **INSTRUCTOR ASSISTANT** in light gray with a gold band sweeping
  right and back, for at least 1 s and for as long as the app is loading (it's in the
  page's HTML). With reduced motion it's plain gold.

Gold `#FFC328` is only ever a fill, with near-black text on it (10.4:1). Gold text on white
would be 1.6:1, so links and the focus ring use a deep gold, `#7A5600` (6.7:1); pale gold
`#FFF4D6` is for highlights and hovers. In dark mode, BYU gold itself is the link and focus
color (about 10:1 on the dark page). The palette is defined once in `globals.css`
(`--ia-*`) and used through Tailwind's `ia-*` colors, so dark mode needs no `dark:` copies.

The icons (bot avatar, favicon, home-screen icons) are upstream's gold path mark,
unchanged. The previous design (the missionary layout in blue) is commit `7b01f20` on
`missionary-design-blue`.

Languages (owner, 2026-10-20): the interface is in **English, Spanish, and Portuguese**
(Settings → Language; with no pick, the browser's language, else English). Every string
is in `app/lib/chrome-strings.ts`; components read it through `useChromeStrings()`. The
welcome cards come from `/config?lang=`. Answers follow the question's language, and the
picked language when the question doesn't make one clear.

Differences from upstream on purpose:
- Source icons are local document/globe icons, not favicons from Google (which sent
  Google every cited domain).
- The source chips and the sources panel list only cited sources, labeled "Instructor
  guide (PDF)" or "External page · host".
- Starter questions show on the welcome screen (upstream fetched but never showed them).
- The student-privacy line is always shown under the question box.

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
| `GET /api/v1/chat/config` | The starter cards on the welcome screen |
| `POST /api/v1/chat/thumbs_request` | Thumbs up/down on an answer (a Langfuse score on its trace) |
| `POST /api/v1/chat/feedback/general` | Settings → Send feedback |
| `POST /api/v1/chat/draft/edit` | "Tweak" in the draft composer |

The request body carries the question, the language preference, and any edited draft. It
never carries a role: the backend serves one audience and ignores a client role.

## What instructors see

- **Welcome:** the greeting, up to 4 starter cards, and the question box.
- **Under the question box, always:** "Don't include student names, IDs, or grades."
  (CLAUDE.md §9.2). At the bottom: where answers come from.
- **Answers:** numbered citation badges (`[^N]`). Hovering one previews the source. The
  chips under the answer name the cited guides and open a panel listing each cited
  passage, numbered like its badge, as "Instructor guide (PDF)" or "External page ·
  host", with a link to it. Sign-in links show a lock and carry "(sign-in required)",
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
