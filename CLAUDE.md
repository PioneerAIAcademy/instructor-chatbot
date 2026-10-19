# CLAUDE.md — instructor-chatbot

The chatbot behind the **BYU-Pathway Instructor Assistant**. It answers questions from
BYU-Pathway **online instructors** (adjunct faculty teaching BYU-Idaho and Ensign College
courses through BYU-Pathway Worldwide), not missionaries. Everything it knows comes from one
Pinecone index, **`instructor-assistant`**, built by the
[`instructor-indexer`](../instructor-indexer/CLAUDE.md) repo.

This repo is a **copied-and-trimmed** successor to
[`PioneerAIAcademy/pathway-chatbot`](https://github.com/PioneerAIAcademy/pathway-chatbot)
(the Missionary Assistant), the same way `instructor-indexer` was cut down from
`pathway-indexer`. Copy only what §4 lists under **Keep** or **Adapt**. Leave out everything else.

> **Status (2026-10-19): Phases 0–4 merged (PRs #1–#5). Phase 5 (observability) in PR #6, with
> review fixes on `phase-5-observability`. Next: Phase 6.** This document is the plan, the repo rules, and the journal (§14).
> Facts marked *(read 2026-10-16)* were read from the code. Re-check them if upstream moves.
> `UPSTREAM.md` lists every file copied from upstream and what changed locally.
>
> **How to read file:line references.** A bare path such as `backend/app/engine/query_filter.py:86`
> points at **pathway-chatbot `main` @ `870cc5b`** (2026-10-05). `indexer:` means
> **instructor-indexer `main` @ `2436a34`** (2026-10-12). **UNVERIFIED** marks anything not
> confirmed from code or data.

---

## 0. Rules

1. **No AI or co-author attribution in commit messages.** No `Co-Authored-By`, no "Generated
   with …", no 🤖, no `noreply@anthropic.com`. Copy `.githooks/commit-msg` from pathway-chatbot
   (it already blocks all of these, `.githooks/commit-msg:21-41`) and run
   `bash scripts/setup-dev.sh` once per clone. **Note:** in pathway-chatbot the hooks exist, but
   `core.hooksPath` is unset on the current checkout, so nothing is enforced until the script runs.
2. **Keep the journal current.** Update §14 at the start, middle, and end of every session
   (`/journal` if installed), so the next developer or agent can start cold.
3. **No agent pushes to `main`.** Work on a branch and open a PR.
4. **No secrets in this file.** This `CLAUDE.md` is meant to be committed (unlike
   pathway-chatbot's local-only journal). Keys live only in `.env`, which is gitignored. Name
   variables here, never values. No internal hostnames that carry credentials.
5. **Audience isolation is a security property, not a feature flag.** Never weaken the role
   filter, the source filter, the index-name guard, or the post-retrieval role check (§7
   Phase 1) to make a test or an eval pass. A guard that fires is a finding.
6. **Pinecone is read-only from this repo.** The chatbot never upserts, deletes, or creates
   indexes. Only `instructor-indexer` writes to `instructor-assistant`.

---

## 1. What it answers from

| Item | Value |
| --- | --- |
| Index | `instructor-assistant`: serverless, `aws/us-east-1`, cosine, 3072 dims. **Already exists.** It lives in a **separate Pinecone account** from the missionary index `pathway` (owner, 2026-10-16). Indexer §8 Q2 still says "same project", so update it there. |
| Contents *(indexer journal 2026-10-12)* | **2,228 vectors**: 968 from the **33 instructor PDFs** (`source="instructor-assistant"`) and 1,260 from **39 public pages** that the PDFs link to (`source="instructor-assistant-linked"`, owned by BYU-Idaho, the Church, Canvas, and others). |
| Every vector | `role="instructor"` (`indexer:src/instructor_indexer/to_markdown.py:37`, `linked.py:373`). |
| Metadata | `url`, `title`, `slug`, `source`, `role`, `sequence` (int, starting at 1, `indexer:store.py:191-193`), `content_hash`, `header_1…header_6`, LlamaIndex `_node_content` / `_node_type` / `doc_id` / `ref_doc_id` (= slug). Linked pages also have `linked_from` (comma-joined slugs). |
| **Not present** | `logical_doc_id`, `logical_doc_label`, `vintage_year`, `vintage_confidence`, `authority_tier`, `doc_type`, `is_linked`, `crawl_status`, `title_tag`, `private`, `index_revised` (§5 shows how each reader behaves). |
| Vector ID | `{slug}#{seq:04d}`. Linked pages: `linked--<host>--<path-slug>#{seq:04d}`. |
| Embedding | OpenAI `text-embedding-3-large`, 3072 dims. Same as the chatbot (`backend/.env.example`, `EMBEDDING_MODEL`/`EMBEDDING_DIM`). |
| Citation URL | `url` = the public PDF on `missionaries.prod.byu-pathway.psdops.com/<slug>`, or the linked page's own URL. |
| Refresh | Manual, owner-triggered (indexer Q3). The chatbot never assumes the index changed. |
| PDF shape | Each PDF opens with `Audience:` and `Purpose:` lines, then `## Key Principles` bullets, `Key Words:`, and `## Resources`. Links stay inline as `[anchor](url)`. **66 distinct SharePoint/OneDrive URLs** sit inline in the 33 PDFs' text. Counted from `indexer:data/runs/2026-10-12T1503/md/`, a local, gitignored run folder. |

Known content gaps the bot must handle honestly:
- **Pay Dates** says "picture of pay schedule", but the PDF contains no picture (indexer Phase 6
  note). The bot can give the two pay days per country, not the per-block schedule.
- **SharePoint pages that aren't exported to PDF** (about 5–8, indexer §8) and two OneDrive
  videos are not indexed. Their links still appear in the PDF text.
- 40 linked URLs are pending in `indexer:data/linked_pending.csv`. Sign-in hosts among them:
  `byupathwayworldwideprod.sharepoint.com` (8), `webmailbyui-my.sharepoint.com` (2, OneDrive),
  `companion.byupathway.edu` (1). `pathwayadmin.byui.edu` (the course directory) needs BYU-Idaho
  credentials, per the *How Do I Find My ACL* PDF itself.

---

## 2. How pathway-chatbot answers a question today *(read 2026-10-16)*

This is the path we copy from. Each step lists what it does and where it lives.

| # | Step | Where |
| --- | --- | --- |
| 1 | The browser calls the backend **directly** (no Next.js API route) with the Vercel AI SDK's `useChat` at `${backend}/api/v1/chat`. | `frontend/app/components/chat-section.tsx:143` |
| 2 | Headers: `Content-Type`, `X-Session-ID`, `X-Timezone`, `X-API-Key`; `X-Device-ID` (FingerprintJS) per request. The session ID is a localStorage UUID that rotates after 30 minutes idle. | `chat-section.tsx:103-111, 227, 421`; `frontend/app/utils/session.ts:8-13, 22-37, 46-67` |
| 3 | **The client picks the role.** `body.data.role = isAcmChecked ? "ACM" : "missionary"`. It comes from the "ACMs Only" pill or `?acm=1`, and is not stored. | `chat-section.tsx:50, 159-165, 216, 398`; `frontend/app/components/ui/chat/chat-input.tsx:343-363` |
| 4 | The API key is `NEXT_PUBLIC_API_KEY`, so it **ships in the browser bundle**. It is a rate-limit and abuse speed bump, **not an access boundary**. | `chat-section.tsx:108`; `backend/app/auth.py:6-43` |
| 5 | `POST /api/v1/chat` handler: slowapi `10/minute` per IP, Langfuse `@observe`, `verify_api_key`. | `backend/app/api/routers/chat.py:321-329`; routers mounted at `backend/main.py:169-175` |
| 6 | Input security screen (max 2,000 chars, pattern and ML risk score). MEDIUM or higher is blocked with a canned reply. LOW is sanitized. **Missionary-specific allowlist**: `PATHWAY_TERMS` includes "gathering", "missionary". | `chat.py:349, 361-448`; `backend/app/security/input_validator.py:43, 72-76, 412-466, 584-591, 676-695` |
| 7 | Role is read **from the request body**: `params.get("role", "missionary")`. | `chat.py:455` (blocked path `:364`) |
| 8 | Gathering-agenda scope: regex and calendar resolution of "PC1xx Week N". | `chat.py:494-498`; `backend/app/engine/agenda_scope.py` |
| 9 | `generate_filters(doc_ids, role, agenda_scope)`: the role is validated against `UserRole {missionary, ACM}`, and an **unknown role silently falls back to `missionary`**. Filter: `role == <role>` AND `private != "true"` (OR the uploaded `doc_id`s), plus an optional exact `title in [...]` agenda pin. | `backend/app/engine/query_filter.py:10-12, 70-143` (fallback `:79-83`, role filter `:86`, private `:89-93`) |
| 10 | Langfuse trace: name `chat`, `session_id` = X-Session-ID, `user_id` = X-Device-ID, tags `language:`, `role:`, `feature:chat`, `source:rag`, `security:*`, `workflow:agentic`; metadata `security_validation`, `geo_data`, `user_language`, `role`. ACM questions get a `"(ACMs Question): "` input prefix. Tags are rebuilt at stream end. | `chat.py:501-505, 516-561, 1138-1142, 1174-1179` |
| 11 | Widget router: one LLM call with calendar, tuition, and tuition-journey tools. Tuition and journey short-circuit before Pinecone. Calendar runs a card pipeline next to RAG. | `chat.py:609-907, 909-1005, 1007-1055` |
| 12 | RAG dispatch: `SupervisorOrchestrator` (B3 agentic: plan, then RAG sub-agent tool loop, then critics) when `SUPERVISOR_ENABLED` (default true), else `RetrievalOrchestrator`. | `chat.py:1278-1333`; `backend/app/engine/supervisor_config.py:18` |
| 13 | Retriever: `index.as_retriever(DEFAULT mode, similarity_top_k=35, sparse_top_k=175, filters)`. The sub-agent reuses `engine._retriever`, then `_recency_rerank`. | `backend/app/engine/__init__.py:30-39`; `backend/app/engine/supervisor_orchestrator.py:1509-1532` |
| 14 | Vector store: one cached, bounded `PineconeVectorStore` per process. It reads `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, and `PINECONE_ENVIRONMENT` (all three required). **`PINECONE_INDEX_HOST`, when set, overrides the index name.** Responses don't carry vector values (egress fix). Read timeout 12 s. | `backend/app/engine/vectordb.py:163, 298-303, 312-349, 98, 136` |
| 15 | Reranking: Voyage `rerank-lite-1`, `top_k=17`, threshold `relevance_score >= 0.21`, 3 retries. Nodes are then grouped by `url`, sorted by `sequence`, and overlapping same-header nodes are merged. If everything falls under 0.21, the context is empty. | `backend/app/engine/custom_condense_plus_context.py:18-45, 138-207` |
| 16 | Recency and authority scoring (B1): multipliers from `vintage_*`, `authority_tier`, and liveness; supersession filter by `logical_doc_id`; source label `[Source: <title> — <year>, <tier>, written for …]`. | `backend/app/engine/recency_aware_engine.py:40-102`; `recency_scoring.py:23-91`; `recency_metadata.py:55-90` |
| 17 | Synthesis prompt: `SYSTEM_CITATION_PROMPT` is **hard-coded** (~8k tokens, missionary persona, tuition facts, block status, and program ladder interpolated in). `CONTEXT_PROMPT` covenant, condense prompt, 24k-token memory. **`SYSTEM_PROMPT` in `.env.example` is never read.** | `backend/app/engine/__init__.py:56-58, 60-308, 313-322, 324-338, 358-369` |
| 18 | Critic and revisor (B2, `CRITIC_ENABLED` default true): seven critics (supersession, conflict, hallucination, tone, cultural_voice, terminology, role), all written for the Missionary Assistant persona. | `backend/app/engine/retrieval_orchestrator.py:155-212`; `backend/app/engine/recency_config.py:47`; `backend/app/engine/supervisor_schema.py:17-20`; `backend/app/engine/critic.py:531-536, 580-606` |
| 19 | Deterministic guards: every claim line gets a `[^N]`, runs of the same citation are collapsed, and **link integrity** strips any URL that isn't in a source node's `url` **or its text** (so inline SharePoint links survive). | `backend/app/engine/grounding_guard.py:70, 102, 167-208, 211-227` |
| 20 | Streaming: Vercel data stream. Annotations: `sources` (each node's `id`, `citation_node_id`, **all metadata**, score, text, `url = metadata["url"]`), `suggested_questions` (an LLM call started in parallel), `events`, `correction`, `date_spans`, `user_language`, and calendar or tuition cards. | `backend/app/api/routers/vercel_response.py:515, 528, 544, 564-592`; `backend/app/api/routers/models.py:163-215` |
| 21 | Citations in the UI: `[^N]` becomes a source button through `citation_node_id`. Titles come from the first present metadata key among `title_tag, logical_doc_label, title, …`. Invalid URLs are dropped, the rest are sorted by score, and a trailing `/` is stripped (the only URL rewrite). | `frontend/app/components/ui/chat/chat-message/markdown.tsx:286-367, 895-940`; `frontend/app/components/ui/chat/chat-message/chat-sources.tsx:23-32, 132-153`; `frontend/app/components/ui/chat/index.ts:360-371` |
| 22 | Feedback: thumbs → `POST /api/v1/chat/thumbs_request {trace_id, value, comment}` → `langfuse.score(name="user_feedback")`. General feedback → its own trace. Screenshots go to Cloudinary folder `missionary-assistant/feedback`. | `frontend/app/components/ui/chat/chat-message/thumb_request.ts:13-33`; `chat.py:1857-1894, 1957, 2004-2044` |
| 23 | Other observability: LlamaIndex → Langfuse bridge (`rag-llm` generations), Sentry (`SENTRY_*`; PII off by default; sample rate 1.0 in dev, else 0.1), request-ID middleware, JSON logs outside dev. The S3 metrics scheduler is built but **never started** (its start call is commented out). | `backend/app/utils/langfuse_llama_index.py:39, 189-222`; `backend/app/settings.py:17-30`; `main.py:15-24, 112, 197-213`; `backend/app/middleware/monitoring_middleware.py:58-164`; `backend/app/observability.py:28-44` |

**UNVERIFIED:** how `private != "true"` behaves on vectors that **lack** `private`. Neither
indexer writes `private`, yet the missionary bot retrieves fine, so Pinecone's `$ne` evidently
matches missing fields. Moot for us: §7 Phase 1 drops the `private` clause. Also UNVERIFIED:
where the frontend is hosted in production (the Dockerfile serves a static export with
`serve -s out`, `frontend/Dockerfile:31`; the env comments mention Vercel).

---

## 3. Architecture decision

**Recommendation: (a) a separate `instructor-chatbot` repo, copied and trimmed from
pathway-chatbot, deployed as its own backend and frontend services, reading only
`instructor-assistant`.** Not (b), an "instructor" mode inside pathway-chatbot.

| Concern | (a) Separate repo + deployment | (b) Mode inside pathway-chatbot |
| --- | --- | --- |
| **Audience isolation** | Strong by construction. The deployment's index holds no missionary vectors, so no client input can retrieve one. The role is pinned on the server. The missionary app never gets an instructor role. | The role is client-chosen today (§2 rows 3, 7) and unknown roles fall back to `missionary` (row 9). The API key is public (row 4). A safe (b) still needs **two deployments with an env-pinned mode**, plus a per-request index switch that must never be client-driven. That is (a)'s deployment cost without (a)'s blast-radius separation. |
| **Deploy separation** | Own services, keys, Langfuse project, Sentry project, rate limits, and release cadence. An instructor change can't take down the missionary bot. | Every release ships both products. A regression in shared prompt code hits missionaries, the larger and more tuned product. |
| **Shared fixes** | Fixes don't flow automatically. Mitigated: the platform files we keep (`vectordb.py`, `input_validator.py`, `grounding_guard.py`, `custom_condense_plus_context.py`, the Langfuse bridge, middleware) are small and stable. They're listed in `UPSTREAM.md` with their source commit, and `scripts/upstream_diff.sh` diffs them against pathway-chatbot `main` on demand (Phase 0). | Fixes are shared automatically. This is (b)'s one real win. |
| **Maintenance cost** | About 3–5k backend lines instead of 27.8k (`find backend/app -name '*.py' \| xargs wc -l`). No calendar, tuition, agenda, or supervisor code to keep green. | The persona is hard-coded in at least 12 modules: `engine/__init__.py:60-308`; `critic.py` (≈107 missionary/ACM/gathering mentions); `rag_subagent.py` (≈36); `supervisor.py`, `presenter.py`, `emit_channel.py`, `audience_signal.py`, `draft_edit.py:128-146`, `suggestion.py:11-23`, `localization.py:119,186`; the glossaries; frontend branding in about 12 files. Every one would need a branch, and every instructor change would run under 1,109 missionary tests, some of which pin prompt text (`tests/test_covenant_prompt_lock.py`). |
| **Upstream sync** | Untouched. | pathway-chatbot is mirrored byte-identically into the ICS repo (local journal). Instructor code would ride along into a repo named "Missionary-ChatBot" and its CodeQL scans. |
| **Team precedent** | Matches: one repo per product (`nmo`, `pathway-role-play`, `instructor-indexer`). | — |

**Engine choice for v1:** port the **classic RAG path**: the `get_chat_engine` wiring,
`CustomCondensePlusContextChatEngine`, Voyage rerank, citation postprocessor, grounding guards,
and a trimmed `RetrievalOrchestrator` without the missionary critic. Leave out the B3 supervisor
stack. Reasons:
- Supervisor, orchestrator, sub-agent, critic, presenter, and emit come to about 5.8k lines,
  routed around calendar, tuition, and temporal tools and tuned with missionary critics.
- The corpus is 2,228 vectors with one flat topic list.
- The indexer's own `verify` already gets hit@5 = 100% with plain similarity.
- Phase 10 brings the agentic path back **only if** the answer eval shows multi-step retrieval
  failures that the classic path can't fix. Upstream's own A/B (`.env.example` comment:
  "Thinking beat Instant 6/8 on completeness") is the reason to keep that door open.

**Do not change pathway-chatbot for this.** In particular, don't add `instructor` to its
`UserRole`. That would let any missionary-app client ask for `role=instructor`. The instructor
corpus lives in another index, so the missionary bot can't reach it either way.

---

## 4. Keep / Adapt / Leave behind

### Keep (copy as-is, minimal edits)

| From pathway-chatbot | Why |
| --- | --- |
| `backend/app/engine/vectordb.py`, `index.py` | Bounded, cached Pinecone client: read timeout, retry cap, `include_values` off (prevents the 2026-08-17 egress 429s). Only add the index guard (Phase 1). |
| `backend/app/engine/node_postprocessors.py` | `node_id` into metadata for citations. |
| `backend/app/engine/custom_condense_plus_context.py` | Condense-plus-context engine, Voyage rerank, url/sequence grouping, merge. Works unchanged on our metadata (`sequence` is an int). Only drop the `audience_marker` call (Adapt below). |
| `backend/app/engine/grounding_guard.py` | Citation coverage, decluster, link integrity. Keeps inline SharePoint links (their URLs are in the node text) and strips invented ones. |
| `backend/app/auth.py`, slowapi limits, the body-size middleware (`main.py:48-96`) | Abuse controls. Same caveat: the API key is public. |
| `backend/app/middleware/monitoring_middleware.py`, `backend/app/observability.py` | Request IDs, 499 on disconnect, JSON logs. |
| `backend/app/langfuse.py`, `backend/app/utils/langfuse_llama_index.py`, `backend/app/settings.py` | Tracing and model/embedding setup. Drop the unused providers if trivial. |
| `backend/app/api/routers/models.py`, `events.py`, `message_variations.py`, `chat_config.py` | Request and response models, `SourceNodes`, status strings, starter questions. |
| Thumbs and general-feedback endpoints (`chat.py:1857-1894, 2004-2044`) | Feedback is the cheapest real-question source. Change the Cloudinary folder to `instructor-assistant/feedback`. |
| `.githooks/`, `.github/workflows/test.yml`, `payload-guard.yml`, `scripts/setup-dev.sh`, both `Dockerfile`s | Repo hygiene and CI parity. |
| Frontend: chat shell, `useChat` wiring, `markdown.tsx` citation mapping, `chat-sources.tsx` sidebar, `UserFeedbackComponent`, general-feedback drawer, i18n infrastructure | The citation UX already links each `[^N]` to `metadata.url`, which for us is the PDF. |

### Adapt (copy, then change)

| Thing | Change |
| --- | --- |
| `query_filter.generate_filters` | Becomes `instructor_filters()`, with no arguments from the client. `role == "instructor"` AND `source in RETRIEVAL_SOURCES`. Drop `UserRole`, `doc_ids`, `private`, `AgendaScope`. |
| `backend/app/api/routers/chat.py` (2,046 lines) | Rewrite to about 300 lines. Keep: security screen, language resolution, Langfuse trace (§9 tags), filters, orchestrator call, `VercelStreamResponse`, thumbs, feedback, draft-edit endpoints. Drop: ACM prefix, agenda scope, widget router, calendar and tuition, geo lookup, `/request`. **Ignore `data.role`**, and log a warning if it's present and isn't `instructor`. |
| `backend/app/engine/__init__.py` | Keep the wiring (top_k 35, sparse 175, memory). Replace `SYSTEM_CITATION_PROMPT`, `CONTEXT_PROMPT`, and the condense prompt with the instructor versions (§8). Remove the tuition, temporal, and program-ladder interpolation. Re-measure the token budget (upstream comment `:340-357`). |
| `custom_condense_plus_context._aretrieve_context` | Replace `audience_marker` with an instructor source label: `[Source: <title> — instructor guide]` for `source=instructor-assistant`, `[Source: <title> — external page (<host>)]` for linked pages. |
| `backend/app/engine/retrieval_orchestrator.py` | Keep the degradation ladder and grounding guards. Use the classic engine, not `get_recency_aware_chat_engine`. Critic off (none ported). Add the login-link annotator (§8.3) and the post-retrieval role assertion (Phase 1). |
| `backend/app/api/routers/vercel_response.py` | Drop the calendar patch builders and calendar error branches (`:954-1107` and the calendar paths in `_event_generator`). Keep text, `sources`, `suggested_questions`, `events`, `user_language`. **UNVERIFIED** what `date_spans` (`:528`) feeds in the UI. Keep it only if it isn't calendar-only. |
| `backend/app/api/services/suggestion.py` | Prompt rewritten for instructors (first person "I", Canvas, blocks, students). |
| `draft_edit.py`, `draft_context.py`, `draft_normalizer.py` | Persona strings changed to the Instructor Assistant; drop the "learners = EnglishConnect" line (`draft_edit.py:135`). Instructors draft announcements and welcome messages (two of the 33 PDFs are about exactly that). |
| `backend/app/security/input_validator.py` | Add instructor terms to `PATHWAY_TERMS` (`instructor`, `adjunct`, `ACL`, `AIM`, `FERPA`, `block`, `syllabus`, `WhatsApp`, `extension`, `grade`) so legitimate questions aren't blocked by the ML-only path (`:431-466`). Re-run the security corpus (`backend/scripts/sec_corpus.json`) to prove nothing got weaker. |
| `backend/app/api/routers/health.py` | `/api/health/ready` also reports the index name and the result of the guard. No vector counts from the API (a read-only stats call is in the operator's script instead). |
| `backend/app/utils/localization.py` | Drop the missionary strings (`:119` gathering agenda, `:186` site index). |
| `backend/scripts/query_chat.py`, `corpus_search.py` | Become `scripts/ask.py` (one question, prints answer, sources, trace ID) and `scripts/retrieve.py` (raw and reranked retrieval with the production filters). |
| Frontend branding and copy | Rebrand about 12 files: `header.tsx`, `chat-avatar.tsx`, `layout.tsx` metadata, `site.webmanifest`, `global-error.tsx`, `greeting.tsx`, `app/lib/chrome-strings.ts` (disclaimer, add the FERPA notice §9.2), `session.ts` storage keys, `settings-menu.tsx` help link, dev banner, console easter egg, `package.json` name. Remove the ACM pill, `?acm=`, and `role` from the body. |
| Starter questions | They're fetched but **never shown** today: they render only with zero messages (`chat-messages.tsx:87`), and the list mounts only after the chat starts (`chat-section.tsx:610`). Fix that, and set 4 instructor starters via `CONVERSATION_STARTERS`. |

### Leave behind (do not port)

| Thing | Why not |
| --- | --- |
| Calendar tool (`backend/app/tools/calendar/`, `CalendarCard.tsx`, `/api/v1/calendar`) | Built for the student academic calendar from Coursedog. Instructors ask about block mechanics, which the PDFs cover. |
| Tuition tool and journey (`backend/app/tools/tuition/`, `TuitionCard`, `TuitionJourneyCard`, `/api/v1/tuition`, the tuition core facts in the prompt) | Missionary or student topic. Not in the instructor corpus. |
| Gathering-agenda scoping (`agenda_scope.py`, `AgendaScope`, `scripts/verify_agenda_titles.py`) | No agendas in the index. |
| ACM role, `UserRole`, the `(ACMs Question)` prefix | Single audience, pinned on the server. |
| Recency and authority scoring (`recency_metadata.py`, `recency_scoring.py`, `recency_config.py` scoring part, `recency_aware_engine.py`) | The index has no classifier fields. Every multiplier is neutral and the labels say "undated, unknown" (§5). Re-add only if the indexer gains vintages. |
| Critic and revisor (`critic.py`, `critic_schema.py`, `audience_glossary.json`, `terminology_glossary.json`) | All seven critics assume the missionary persona (`critic.py:531-536, 588-606`). After the Phase 6 baseline, consider a single grounding (hallucination) critic written for instructors. |
| B3 agentic stack (`supervisor*.py`, `rag_subagent.py`, `presenter*.py`, `emit_channel.py`, `emit_strings.py`, `pushback.py`, `response_brief.py`, `rtf_brief.py`, budget) | See §3 engine choice. Optional, Phase 10. |
| Audience signal (`audience_signal.py`) | It flags missionary-only tools (My Gatherings, Learner Progress Report). |
| Temporal block status and live block dates (`temporal.py`, `academic_calendar_dates.py`, `program_ladder.py`) | **UNVERIFIED** whether Worldwide Online instructors follow the same block dates as the student calendar this reads. Keep only "today's date" in v1 (Q8). |
| `context_cleaning.py` rules | Both rules target missionary-corpus artifacts ("J 321", Help Center CTA). |
| Uploads, LlamaCloud, loaders, `generate.py`, file server (`/api/v1/chat/upload`, `/api/files/data`, `LlamaCloudSelector`) | The index is built only by instructor-indexer. No private docs. |
| Dictation (`backend/app/dictation/`, `/api/v1/dictation`, the frontend dictation UI) | Not needed for v1 (Q10). |
| Geoapify geo lookup | Used only as a language tiebreaker. Instructors set a language preference. |
| S3 metrics upload and heartbeat (`monitoring.py`, `scheduler.py`) | Never started upstream (`main.py:197-213`). Langfuse and Sentry cover v1. |
| T-Systems LLM hub (`llmhub.py`), Ollama/Azure branches if unused | Not used. |
| The ~70 missionary tests | Port only tests of Keep/Adapt modules: `test_vectordb_client.py`, `test_grounding_guard.py`, `test_link_integrity_prompts.py` (adapted), the input-validator tests, `test_monitoring_middleware.py`, `test_langfuse_llama_index_handler.py`. |
| Notebooks, `output_data.csv`, `monitoring_reports/`, `bench*`, `RECOMMENDATIONS.md`, `GC_IMPLEMENTATION.md` | Not runtime. |

---

## 5. Index contract (consumer side) and missing classifier fields

These must match indexer §5. The chatbot **checks them at startup** (Phase 1) instead of
assuming them.

| Setting | Chatbot side |
| --- | --- |
| Index | `PINECONE_INDEX_NAME=instructor-assistant`. Boot fails unless the name is in `ALLOWED_INDEX_NAMES`. If `PINECONE_INDEX_HOST` is set, it must be that index's host, or boot fails. The check parses the index name out of the host (`<name>-<project-id>.svc…pinecone.io`); a plain prefix match would accept `instructor-assistant-staging-…` for `instructor-assistant`. This closes the override in `vectordb.py:298-302`. |
| Embedding | `EMBEDDING_MODEL=text-embedding-3-large`, `EMBEDDING_DIM=3072`. |
| Reader pins | Upstream lock: `llama-index-core 0.10.58`, `llama-index-vector-stores-pinecone 0.1.9`, `pinecone-client 5.0.1` (`backend/poetry.lock`). **Langfuse is `4.16.0`, not upstream's `2.60.10`** (Phase 5): 2.x's ingestion API is shut down on Langfuse Cloud on 2026-11-16, and new organizations can't read its data. The indexer writes with `vector-stores-pinecone 0.1.3` and `pinecone-client <4`. The `_node_content` format is the same, so **reading works across these versions**. Phase 1's smoke test proves it on the live index. |
| Filter | `role == "instructor"` AND `source in ["instructor-assistant", "instructor-assistant-linked"]`. Nothing from the client takes part. |

How each upstream reader behaves when the classifier fields are missing:

| Reader | Field(s) | Behavior on the instructor index | Decision |
| --- | --- | --- | --- |
| `recency_metadata.parse_recency_signals` (`:55-90`) | all | Never raises. Confidence → `low`, authority → `unknown`, doc_type → `other`, `is_linked` → true, crawl_status → `unknown`. | Not ported. |
| `recency_scoring.compute_final_score` (`:23-55`) | `vintage_*`, `authority_tier` | Recency 1.0 (low confidence), authority 0.9 (`unknown`), liveness 1.0. **Every node is scaled by 0.9 and the order doesn't change.** | Not ported (no effect). |
| `recency_scoring.apply_supersession_filter` (`:58-91`) | `logical_doc_id` | Empty → nothing dropped. | Not ported. |
| `recency_aware_engine._vintage_label` (`:40-62`) | `logical_doc_label`, `vintage_year`, `authority_tier`, `role` | Label becomes `[Source: <title> — undated, unknown]`. `instructor` isn't in `_AUDIENCE_ROLES` (`:33-37`), so there's no audience clause. "undated, unknown" invites the model to hedge, and the missionary prompt's SOURCE LABELS section (`__init__.py:83-86`) tells it to talk about vintage. | **Replaced** by the instructor source label (§4 Adapt). |
| `supervisor_orchestrator._default_pinecone_query` with `target_year` (`:1436-1507`) | `vintage_year` | Filter `vintage_year == "<year>"` → **zero matches**, returned as an empty list (the `except` only catches exceptions) → **false "couldn't find it"** whenever the planner reads a year into a question ("the 2026 pay dates"). | Not ported. If Phase 10 ports it: `target_year` must be forced to `None`. |
| `supervisor_orchestrator._fetch_doc_sections` (`:1535-1616`), `rag_subagent` broad dig (`:815-835`) | `logical_doc_id` | `doc_ids` is empty, so the section-diverse fetch never fires and broad questions rely on similarity only. | Not ported. If Phase 10: key on `slug` instead. |
| `critic._format_chunks` (`critic.py:106-117`) | `vintage_year`, `role` | Prints `vintage_year=unknown`, `role=instructor`, which feeds missionary-only critic rules. | Not ported. |
| `audience_signal` identity fields (`:33-40`) | `logical_doc_label`, `title_tag` | Falls through to `title` and `header_*`. | Not ported. |
| Frontend title (`chat-sources.tsx:23-32`) | `title_tag`, `logical_doc_label` | Falls through to `title`. Correct. | Keep. |
| `_organize_nodes` (`custom_condense_plus_context.py:190-207`) | `url`, `sequence` | Both present. Grouping and ordering work as designed. | Keep. |

---

## 6. Target layout

```
instructor-chatbot/
├── CLAUDE.md                        ← this file
├── UPSTREAM.md                      ← every Keep/Adapt file: upstream path, upstream commit, local changes
├── .claude/agents/chatbot-operator.md
├── .githooks/{commit-msg,pre-push,post-commit}
├── .github/workflows/{test.yml,payload-guard.yml}
├── scripts/{setup-dev.sh,upstream_diff.sh}
├── backend/
│   ├── .env.example                 ← names only (§11)
│   ├── API.md                       ← Phase 4: the stream contract the frontend builds against
│   ├── Dockerfile, pyproject.toml, poetry.lock   ← Python 3.12, upstream pins
│   ├── main.py                      ← routers: /api/v1/chat (+ /config), /api (health)
│   ├── app/
│   │   ├── auth.py, langfuse.py, settings.py, observability.py
│   │   ├── security/input_validator.py
│   │   ├── middleware/monitoring_middleware.py
│   │   ├── utils/langfuse_llama_index.py, localization.py (trimmed)
│   │   ├── api/routers/{chat.py,chat_config.py,events.py,health.py,models.py,vercel_response.py,message_variations.py}
│   │   ├── api/services/{suggestion.py,draft_edit.py}
│   │   └── engine/
│   │       ├── __init__.py          ← get_chat_engine + instructor prompts
│   │       ├── prompts.py           ← instructor system / context / condense prompts (§8)
│   │       ├── audience_guard.py    ← instructor_filters(), index guard, post-retrieval role assertion
│   │       ├── login_links.py       ← sign-in link annotator (§8.3)
│   │       ├── vectordb.py, index.py, node_postprocessors.py
│   │       ├── custom_condense_plus_context.py, grounding_guard.py
│   │       └── retrieval_orchestrator.py
│   ├── scripts/{ask.py,retrieve.py,eval_retrieval.py,eval_answers.py}
│   └── tests/
│       ├── test_audience_guard.py   ← filter shape, client role ignored, index/host guard, role assertion
│       ├── test_login_links.py, test_prompts_lock.py, test_grounding_guard.py, test_vectordb_client.py, …
│       └── eval/{questions.yaml,results/}   ← results/ gitignored
└── frontend/                        ← Phase 8 only: Next.js static export, rebranded, ACM/calendar/tuition removed
```

---

## 7. Build plan

**Backend first.** Part A (Phases 0–7) builds, evaluates, and stages the backend on its own,
checked with scripts and `curl`, with no browser involved. Part B (Phases 8–9) starts only after
Phase 7's "Backend done" gate, and builds the frontend against a backend whose API is already
fixed. Phase 10 is optional and comes last.

Each phase ends with offline tests passing and its **Done when** met. Don't start a phase before
the previous one is done. Live calls (OpenAI, Voyage, Pinecone reads) are opt-in, behind
`RUN_LIVE_TESTS=1`.

### Part A — Backend

### Phase 0 — Backend scaffold
- New repo, **backend only**. Copy the §4 Keep and Adapt backend files (not yet adapted) from
  pathway-chatbot `870cc5b`, plus hooks, `payload-guard.yml`, `setup-dev.sh`, the backend
  `Dockerfile`, and `pyproject.toml`/`poetry.lock`. Prune deps for left-behind modules:
  voyageai stays; `llama-cloud` goes; `cloudinary` stays only if feedback screenshots stay on.
  `frontend/` isn't copied until Phase 8.
- `test.yml` with the **backend job only**. The frontend job is added in Phase 8.
- Write `UPSTREAM.md` and `scripts/upstream_diff.sh <pathway-chatbot path>`. The script prints
  `git diff --stat` per tracked file against upstream `main`. It's read-only and needs no network.
- `backend/.env.example` with names only (§11).
- **Done when:** `poetry run pytest -q` passes on a clean clone with no keys; the commit hook
  rejects a `Co-Authored-By` line; `grep -rniE 'tuition|calendar|agenda|ACM' backend/app` only
  hits intentional comments, listed in `UPSTREAM.md`.

### Phase 1 — Audience lock and index switch
- `audience_guard.py`:
  - `instructor_filters()` → `MetadataFilters([role == "instructor", source in RETRIEVAL_SOURCES], and)`.
  - `check_index_config()` runs at startup and in `/api/health/ready`. Boot fails if
    `PINECONE_INDEX_NAME ∉ ALLOWED_INDEX_NAMES`, or if `PINECONE_INDEX_HOST` is set and doesn't
    start with `<name>-`.
  - `assert_instructor_nodes(nodes)` runs after retrieval. It drops any node whose `role` isn't
    `instructor` or whose `source` isn't allowed, logs `ERROR audience_leak`, and tags the trace
    `guard:audience_leak`. This should never fire. It's defense in depth.
- `chat.py` never reads `data.role`.
- `scripts/retrieve.py "<q>"` prints the top 35 raw and top 17 reranked, with slug, source, role,
  score.
- **Done when:**
  - Unit tests cover: the same filter for `role` ∈ {absent, `missionary`, `ACM`, `instructor`,
    `garbage`}; boot refuses `PINECONE_INDEX_NAME=pathway`; boot refuses a host that doesn't
    match; the role assertion drops a planted `role=missionary` node.
  - Live: `retrieve.py` on 5 questions returns only `role=instructor` nodes from
    `instructor-assistant[-linked]`, and the expected slug is in the top 5 for all 5.
  - Live: the same 5 against `PINECONE_INDEX_NAME=pathway` don't start (guard), proving the
    switch is the env var and nothing else.

### Phase 2 — Retrieval path and retrieval eval
- Classic engine (top_k 35, sparse 175, Voyage `rerank-lite-1` top 17 at ≥ 0.21), instructor
  source labels, no recency scoring.
- `scripts/eval_retrieval.py` runs `tests/eval/questions.yaml` through the **production
  retriever plus rerank** (not raw Pinecone, unlike indexer `verify`). It reports hit@5 after
  rerank, the number of questions where rerank dropped everything below 0.21, and the rank of
  the first expected slug. It writes `tests/eval/results/<ts>-retrieval.json`.
- **Done when:** hit@5 after rerank ≥ **90%** on the DRAFT set (§10); 0 empty-context questions;
  0 non-instructor nodes. If rerank is the cause of misses, record it and leave the 0.21
  threshold alone until the answer eval shows the effect (Q15).

### Phase 3 — Instructor prompt, tone, citations, sign-in links
- `prompts.py` with the §8 prompts. A prompt-lock test pins the load-bearing sentences (sign-in
  rule, no reading claims, FERPA, citation format).
- `login_links.py` (§8.3), applied after `apply_grounding_guards`.
- **Done when:**
  - Offline: tests for citation coverage, link integrity on SharePoint links, the login
    annotator (adds the note once, idempotent, skips links already annotated, skips non-login
    hosts), and prompt lock all pass.
  - Live: `scripts/ask.py` on the 4 sign-in questions in §10 gives answers that cite the PDF,
    mark every SharePoint/OneDrive/course-directory link as needing sign-in, and never say the
    page was read.

### Phase 4 — Chat API and streaming
- Trimmed `chat.py` and `vercel_response.py` (§4 Adapt), thumbs and general-feedback endpoints,
  draft edit, and `/api/v1/chat/config` serving the 4 starters from `CONVERSATION_STARTERS`.
- Write `backend/API.md`: request body and headers, every streamed annotation type and its
  fields (`sources` with `url`, `title`, `source`; `suggested_questions`; `events`;
  `user_language`), and the error shapes. This is the contract Part B builds against.
- **Done when (checked with `curl` and `scripts/ask.py`, no browser):**
  - The SSE stream carries the answer text, a `sources` annotation whose `url` is the PDF URL
    (`missionaries.prod.byu-pathway.psdops.com/<slug>`) or the linked page's URL, and
    `suggested_questions`.
  - Every `[^N]` in the text matches a source's `citation_node_id`.
  - A body with `data.role="missionary"` returns the same sources as one without it (§10 G4).
  - `POST /api/v1/chat/thumbs_request` with a trace ID returns 200. Draft edit works.
  - `/api/docs` lists only the kept routes (no tuition, calendar, dictation, or upload).
  - `API.md` matches what the stream actually sends.

### Phase 5 — Observability
- Langfuse and Sentry per §9. Separate Langfuse project and Sentry project (Q5).
- **Done when:** one local question produces a trace named `chat` with tags `app:instructor-assistant`,
  `role:instructor`, `index:instructor-assistant`, `feature:chat`, `workflow:classic`,
  `language:<xx>`, `security:*`; metadata `index_name`, `sources_core`, `sources_linked`,
  `login_links`, `app_version`; the `rag-llm` generation nested under it; and a thumbs score
  (posted with `curl`) on it. Eval traffic carries `eval` and `eval_run:<id>`, so dashboards can
  exclude it. No secret or key appears in any trace, log line, or Sentry event (grep the local
  logs).

### Phase 6 — Answer eval and baseline
- `scripts/eval_answers.py` posts each §10 question to the local `/api/v1/chat` (SSE parsing as in
  upstream `scripts/query_chat.py`), with `X-Session-ID: eval-<run>`. Deterministic checks per
  question:
  1. at least one cited source has a slug in `expect`;
  2. every `[^N]` resolves to a returned source;
  3. all sources have `role=instructor`;
  4. `must_include` phrases (any-of groups, case-insensitive);
  5. no `must_not` phrases (global: "missionar", "gathering", "ACM", "Student Portal" as an
     instructor action, "I read", "I checked", "I opened");
  6. every sign-in link has the sign-in note;
  7. refusal questions refuse.
- An optional LLM-judge groundedness score sits behind `RUN_LLM_JUDGE=1`. It reports only and
  never gates.
- **Done when:** ≥ **85%** of answer questions pass all checks, **100%** of guard questions pass,
  and the result is recorded in §14 with the results-file name. Still DRAFT until real
  questions arrive (Q14).

### Phase 7 — Backend staging deploy ("Backend done" gate)
- Separate backend service (Docker, `ENVIRONMENT=prod`, `API_KEYS` set, `CORS_ALLOW_ALL=false`),
  using the instructor Pinecone account's key and the instructor Langfuse and Sentry projects.
  `ALLOWED_ORIGINS` stays empty or local-only until the frontend has a URL (Phase 8).
- **Done when:** the answer eval passes against the **staging** backend; `/api/health/ready`
  shows `index=instructor-assistant, guard=ok`; a request with `role=missionary` in the body
  behaves exactly like one without it; staging traces land in the instructor Langfuse project;
  the missionary deployment's env is unchanged. **Part B starts only after this.**

### Part B — Frontend

### Phase 8 — Frontend
- Copy `frontend/` and trim it per §4: rebrand the ~12 files; remove the ACM pill, `?acm=`, and
  `role` from the body; remove the calendar, tuition, dictation, upload, and LlamaCloud UI.
  Show starters on an empty chat. Put the FERPA notice under the input (§9.2). Label sources in
  the sidebar as "Instructor guide (PDF)" or "External page · <host>" (§8.3). Handle only the
  annotation types in `backend/API.md`.
- Add the frontend job to `test.yml`.
- **Done when:**
  - Local frontend (`:3000`) against the local or staging backend: an answer streams, `[^N]`
    buttons open the sources sidebar, each source links to its PDF or page, linked-page sources
    show their host, thumbs record a score on the trace, and a drafted message renders in the
    draft composer.
  - `npm run build`, `tsc --noEmit`, and `lint` are clean.
  - `grep -rniE 'missionar|ACM|gathering' frontend/app` returns only intentional matches.

### Phase 9 — End to end and production
- Frontend build with its own `NEXT_PUBLIC_*`. Set the backend's `ALLOWED_ORIGINS` to that
  frontend only. Promote both to production.
- **Done when:** the answer eval passes against the production backend; a manual run of 5 §10
  questions through the production UI shows correct citations and sign-in labels; CORS rejects
  any other origin; the missionary deployment is unchanged.

### Phase 10 — Optional: agentic retrieval
- Only if Phase 6 failures are multi-step retrieval misses (the answer needs two documents, or a
  broad "what's in X" question). Port the supervisor and sub-agent with `target_year` forced to
  `None` and the section fetch keyed on `slug`. Write instructor critics, or none.
- **Done when:** the answer eval improves by ≥ 5 points with no guard regressions, and p95
  latency is recorded.

---

## 8. Prompt, tone, citations, sign-in links

### 8.1 Tone
- A colleague in instructor support talking to adjunct faculty. Address the instructor as
  **"you"**. This is the opposite of the missionary prompt's "avoid second-person" rule
  (`__init__.py:68`).
- Action first. Short. Steps as numbered lists when there are 2 or more.
- Warm about students, never preachy. The gospel-connection PDFs are content to cite, not a
  voice to adopt.
- "Students" means BYU-Pathway online students. Use the corpus's terms: ACL (Assistant Course
  Lead), AIM (Assistant Instructor Manager), TGL (Teaching Group Leader), block (7 weeks;
  Winter = blocks 1 & 2, Spring = 3 & 4, Fall = 5 & 6, per *How Do I Find My ACL*), Week 07,
  UTC, Canvas, Help Center, Online Instructor Support Line.

### 8.2 Instructor system prompt (draft, Phase 3 finalizes it)

```text
Today's date is {current_datetime}.

ROLE & AUDIENCE
You are the BYU-Pathway Instructor Assistant. You help online instructors (adjunct faculty
teaching BYU-Idaho and Ensign College courses through BYU-Pathway Worldwide) with teaching,
course administration, student support, and instructor policies. Speak to the instructor as
"you". Be concise and practical: lead with what to do, then why.

GROUNDING
Answer only from the numbered contexts. Three cases:
1. Contexts cover it: answer and cite each claim inline with [^N], then stop.
2. Contexts partly cover it: answer what they say, add one short sentence on what they don't.
3. Nothing relevant: say so in 1-2 sentences, and point to the Online Instructor Support Line
   only if a context links it. Never answer from general knowledge.

CITATIONS
Put [^N] right after the sentence it supports. Never cite a context for a claim it doesn't
make. Never put [^N] inside a drafted message.

SIGN-IN LINKS
Some links inside the contexts go to pages that need a BYU-Pathway or BYU-Idaho sign-in
(SharePoint, OneDrive, the course directory, the Companion app, the student portal). You
have NOT read those pages. You only have the text of the instructor guide that links to them.
- You may give the link, labeled as needing sign-in, and cite the guide it came from.
- Never summarize, quote, or describe what such a page says unless a context contains that text.
- Never say you opened, read, checked, or reviewed a linked page.
- If asked about one, say it's behind a sign-in, give the link, and share what the guide
  itself says about it.

EXTERNAL PAGES
Contexts labeled "external page" come from other organizations (BYU-Idaho, the Church,
Canvas). Say whose page it is. If one disagrees with an instructor guide, follow the guide
and mention the difference.

INSTITUTIONS
Some guides give different rules for BYU-Idaho and Ensign College courses. If the question
doesn't say which, give both (labeled) or ask which institution the course belongs to.

STUDENT PRIVACY (FERPA)
Never ask for a student's name, ID, grades, or other records. If the instructor shares them,
don't repeat them back; answer the general question. For requests from parents or third
parties, follow the FERPA guide in the contexts.

DRAFTS
When asked to write an announcement, welcome message, or email to students, put only the
send-ready text in a ```message or ```email fence: plain text, no markdown, placeholders like
[Student Name], [Course], [Your Name]. Put the guidance and citations outside the fence. Base
it on the cited guidance (for example, the welcome-message and announcement guides).

LINKS
Only give URLs that appear in the contexts.

OUT OF SCOPE
Not general knowledge, homework help, scripture summaries, or legal or HR advice beyond the
guides. Refuse briefly and stop.
```

Plus `CONTEXT_PROMPT`, a shortened version of the upstream covenant (`__init__.py:313-322`)
with the missionary aliases removed. The condense prompt is upstream's, with "missionary"
references removed.

### 8.3 Citations and sign-in links
- **Format:** inline `[^N]` markers. The upstream frontend already maps them to source buttons
  and a sidebar that links each source to `metadata.url` (§2 rows 20–21). For the 33 documents,
  that URL **is the PDF**. For linked pages, it's the page itself. No URL rewriting.
- **Source labels to the model:** `[Source: <title> — instructor guide]` or
  `[Source: <title> — external page (<host>)]`.
- **Sidebar:** show "Instructor guide (PDF)" or "External page · <host>" under the title.
  Use `source` from metadata (already in the `sources` annotation).
- **Deterministic backstop (`login_links.py`):** after the grounding guards, find every markdown
  link or bare URL whose host matches `LOGIN_LINK_HOSTS` (suffix match, so `*.sharepoint.com` is
  covered). Append ` (sign-in required)` once, localized through the existing string tables
  **in the answer's language**, unless a sign-in label already follows the link directly
  (only spaces, `[^N]` markers, or bold in between). A label is one of the localized labels or
  a strict English form ("requires a BYU login"). A parenthetical that merely mentions signing
  in, such as "(sign in to WhatsApp Web first)", is not a label. Count the
  sign-in links into trace metadata `login_links` and the labels added into
  `login_links_labeled`. The prompt does the explaining, and tells the model **not** to write
  the note itself. This guarantees the label. *(Revised in the Phase 3 review, 2026-10-19.)*
- The bot **never fetches** a link at answer time. There is no browsing tool, and none will be
  added. Unindexed pages are the indexer's pending list (indexer §8, Q5), not a chatbot problem.

---

## 9. Observability and privacy

### 9.1 Langfuse
- **Separate Langfuse project** for the Instructor Assistant (Q5), with its own
  `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. Even so, tag everything, so traces stay
  identifiable if the projects are ever merged.
- Trace `chat`: `session_id` = X-Session-ID, `user_id` = X-Device-ID (as upstream). With
  langfuse 4.x (Phase 5), Langfuse's first-class `environment` = `ENVIRONMENT` and `release` =
  `APP_VERSION`. Upstream's 2.x code sent `release` = `ENVIRONMENT`.
- Tags: `app:instructor-assistant`, `role:instructor`, `index:<PINECONE_INDEX_NAME>`,
  `feature:chat`, `workflow:classic`, `language:<xx>`, `security:<clean|risk_*>`. Plus `eval` and
  `eval_run:<id>` when the session ID starts with `eval-`. Plus `guard:audience_leak` if the
  Phase 1 assertion ever fires.
- Metadata: `role`, `index_name`, `sources_core` and `sources_linked` (counts by `source`),
  `cited_slugs`, `login_links`, `rerank_empty` (bool), `app_version` (`APP_VERSION`, the git
  SHA set at build).
- Scores: `user_feedback` from thumbs (unchanged). Eval runs may post `eval_pass` (0/1) on their
  own traces.
- Keep `draft_edit` traces, and add the same `app:` and `role:` tags (upstream sets no role there,
  `chat.py:1702-1717`).

### 9.2 Student privacy (FERPA)
Instructors will paste student names, IDs, and situations into questions. Those prompts go to
OpenAI, Voyage, Langfuse, and possibly Sentry.
- UI notice under the input: "Don't include student names, IDs, or grades." (`chrome-strings.ts`,
  translated).
- Redact before tracing: emails and digit runs of 7 or more (student IDs) in the Langfuse trace
  input and output and in logs.
  - **Resolved, Phase 5 (langfuse 4.16.0):** `app/redaction.py` is the client's `mask`. In 4.x
    that covers the **input, output, and metadata** of every observation, including `rag-llm`
    prompts.
  - URLs are cut out first and kept whole. Markdown link labels are masked. Dates such as
    2026-10-23 are left alone.
  - IDs written `#12345678`, `ID-12345678`, `id=12345678`, or `+1.801.555.1234` are masked.
  - Thumbs comments are redacted explicitly (scores aren't observations).
  - Logs carry no question text (Phase 4).
  - Names can't be masked by pattern, so metadata still never carries the question (a test
    enforces it).
- `SENTRY_SEND_PII=false` (upstream default). Never attach request bodies to Sentry events:
  `max_request_body_size="never"`, `include_local_variables=False` (stack locals hold the
  question), and `before_send` / `before_breadcrumb` hooks that redact exception values, the
  event message, log entries, and breadcrumbs (log lines recorded by Sentry's logging
  integration).
- Langfuse data retention for this project: Q17.

---

## 10. Eval questions — **DRAFT**

> **DRAFT, 2026-10-16.** Written from the 33 PDF titles and their Key Principles, not from real
> instructor traffic. Replace or extend with real questions from the instructor support team
> (Q14), and from thumbs-down traces once live. In Phase 2 these move into
> `backend/tests/eval/questions.yaml` (`q`, `expect` slugs, `must_include` any-of groups,
> `must_not`, `kind`). `must_include` values below are what the PDF says *today*. If the indexer
> re-crawls a changed PDF, re-check them.

Slug suffix `-ia` is omitted below for width. Add it back in the YAML.

| # | Question | Expect (slug) | Must include (any of) | Kind |
| --- | --- | --- | --- | --- |
| 1 | When do Worldwide Online instructors in the US get paid? | `pay-dates-for-worldwide-online-instructors` | "8th" and "23rd" | answer (+ honest gap: no per-block schedule) |
| 2 | I teach from Brazil. Which days of the month am I paid? | `pay-dates-for-worldwide-online-instructors` | "15th" and "30th" | answer |
| 3 | What's the latest I can extend a BYU-Idaho student's due date at the end of the block? | `end-of-block-due-dates` | "Saturday" and ("Week 07" or "Week 7") | answer |
| 4 | How do I give just one student more time on an assignment in Canvas? | `extending-due-dates-for-students-removing-late-penalties-excusing-assignments` | "Canvas" | answer |
| 5 | A student's mother emailed asking about her son's grade. Can I tell her? | `ferpa-adjunct-faculty-responsibilities` | "consent" or "FERPA" | answer |
| 6 | I think a student plagiarized part of an essay. What should I do first? | `academic-integrity` | "benefit of the doubt" or "open mind" | answer |
| 7 | How should I write a due date so students in other time zones understand it? | `what-is-utc-and-why-do-we-use-it-in-our-courses` | "UTC" and "11:59" | answer |
| 8 | How can I tell whether my course uses a textbook? | `understanding-textbooks-in-online-courses` | "Modules" or "Textbook Information" | answer |
| 9 | How do I find my ACL and the other instructors in my course group? | `how-do-i-find-my-acl-other-instructors` | "course directory" and "BYU-Idaho" | sign-in (course directory) |
| 10 | A student's Help Center ticket has had no answer for weeks. How do I escalate it? | `escalation-form-for-unresolved-student-issues` | "escalation form" and ("ticket" or "ID") | answer |
| 11 | A student keeps posting disrespectful comments in discussions. What do I do? | `disruptive-students-principles-resources-reporting`, `student-support-and-escalation-of-issues` | "report" or "Dean of Students" | answer |
| 12 | A student says they have an accommodation for extra time. What am I required to do? | `students-with-accessibility-issues`, `dean-of-students-office-resource-overview` | "accommodation" | answer |
| 13 | A student joined my course late. How do I help them catch up? | `managing-student-adds-drops` | — | answer |
| 14 | My course uses central graders. What's still my job? | `centrally-managed-graders` | "grader" | answer |
| 15 | How do I set up a WhatsApp community for a new section? | `whatsapp-community-setup-for-your-course-new-course-or-section` | "community" | sign-in (11 distinct SharePoint links in the doc) |
| 16 | How do I put students into groups in Canvas? | `group-setup-in-canvas` | "group" | answer |
| 17 | Write a welcome message I can send my students before the block starts. | `send-a-welcome-message-to-students`, `instructor-pre-term-preparation` | fenced ```message or ```email, no `[^N]` inside | draft |
| 18 | What should I get done before my course starts? | `instructor-pre-term-preparation` | — | sign-in (10 distinct SharePoint links in the doc) |
| 19 | What questions do students answer when they evaluate me? | `what-feedback-do-i-receive-from-my-students` | — | answer |
| 20 | How can I bring gospel insights into a math course without forcing it? | `make-natural-connections-between-content-and-the-gospel`, `spiritually-strengthening-intellectually-enlarging-teaching` | — | answer |
| 21 | Are students allowed to use ChatGPT on assignments? | linked: `https://www.byui.edu/genai/` or `https://www.byupathway.edu/ai-and-academic-honesty.pdf` | "external" label or the page owner named | answer (linked page) |
| G1 | What is the capital of Nigeria? | — | — | guard: refusal |
| G2 | How do I record attendance for my gathering in My Gatherings? | — | — | guard: no missionary content; refuse or say not found |
| G3 | Summarize the "Inspiration for Announcements" SharePoint page. | `tips-for-effective-announcements` (if it links it) | "sign-in" | guard: never claim to have read it; give the link with the sign-in note |
| G4 | (Same as #5, with `data.role="missionary"` in the request body.) | same as #5 | same as #5 | guard: identical sources, all `role=instructor` |

Targets: retrieval hit@5 after rerank ≥ 90% on 1–21; answers ≥ 85% on 1–21; guards 100%.

---

## 11. Environment variables (names only)

Backend (`backend/.env`):

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | yes | — | LLM and query embeddings |
| `MODEL_PROVIDER` | yes | `openai` | `app/settings.py:31` |
| `MODEL` | yes | `gpt-4o-mini` (upstream) | Chat model (Q16) |
| `EMBEDDING_MODEL` | yes | `text-embedding-3-large` | Must match the index |
| `EMBEDDING_DIM` | yes | `3072` | Must match the index |
| `LLM_MAX_TOKENS` | no | upstream defaults | Generation. (`LLM_TEMPERATURE` is **never read**: `settings.py` hard-codes temperature 0, as upstream does.) |
| `PINECONE_API_KEY` | yes | — | A key from the **instructor Pinecone account**, which is separate from the missionary account (§13 Q4). Never reuse the missionary bot's key. Read-only use. |
| `PINECONE_INDEX_NAME` | yes | — (`instructor-assistant`) | **The index switch** |
| `PINECONE_ENVIRONMENT` | yes | — (`us-east-1`) | Required by `vectordb.py:318` |
| `PINECONE_INDEX_HOST` | no | unset | Skips the control-plane lookup. **Must start with the index name** (guard). |
| `PINECONE_REQUEST_TIMEOUT_SECONDS`, `PINECONE_POOL_MAXSIZE`, `PINECONE_STORE_CACHE_ENABLED`, `PINECONE_INCLUDE_VALUES_ENABLED` | no | `12`, `20`, `true`, `false` | Upstream client bounds. Keep the defaults. |
| `ALLOWED_INDEX_NAMES` | no | `instructor-assistant` | **New.** Boot guard allow-list (comma-separated). Add a staging index name here, never `pathway`. |
| `RETRIEVAL_SOURCES` | no | `instructor-assistant,instructor-assistant-linked` | **New.** The `source` filter. Dropping the linked source is allowed. Adding any other value is a code-review decision. |
| `LOGIN_LINK_HOSTS` | no | `sharepoint.com,companion.byupathway.edu,pathwayadmin.byui.edu,portal.byupathway.edu` | **New.** Suffix match for the sign-in annotator (§8.3) |
| `VOYAGE_API_KEY` | yes | — | Reranker |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | yes in prod | — | Instructor Langfuse project |
| `LANGFUSE_LLAMAINDEX_ENABLED` | no | `true` | `rag-llm` generations |
| `APP_VERSION` | no | unset | **New.** Git SHA in trace metadata |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_SEND_PII` | no | —, `production`, `false` | Errors. Keep PII off. |
| `ENVIRONMENT` | yes | `dev` | `prod` hides error details and sets JSON logs |
| `API_KEYS` | yes in prod | — | `X-API-Key`. Not a secret from users (it ships in the frontend). |
| `ALLOWED_ORIGINS`, `CORS_ALLOW_ALL` | yes | —, `false` | The instructor frontend only |
| `APP_HOST`, `APP_PORT` | no | `0.0.0.0`, `8000` | uvicorn |
| `CONVERSATION_STARTERS` | no | unset | Newline-separated starter questions |
| `CLOUDINARY_URL` (or `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET`) | no | unset | Feedback screenshots, if kept |
| `RUN_LIVE_TESTS`, `RUN_LLM_JUDGE` | no | unset | Opt-in billable tests and eval judge |

Frontend (`frontend/.env`, build-time): `NEXT_PUBLIC_CHAT_API`, `NEXT_PUBLIC_API_KEY`,
`NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT`;
dev-only `DEV_PROXY_BACKEND`; CI-only `SENTRY_AUTH_TOKEN`. Not carried over:
`NEXT_PUBLIC_USE_LLAMACLOUD`, `GEOAPIFY_API_KEY`, `LLAMA_CLOUD_*`, `AWS_*`/`MONITORING_*`,
`TUITION_*`, `BLOCK_DATES_*`, `CALENDAR_*`, `SUPERVISOR_*`, `RAG_SUBAGENT_*`, `EMIT_*`,
`PRESENTER_*`, `CRITIC_*`, `DICTATION_*`, `SYSTEM_PROMPT`/`TOP_K`/`STREAM_TIMEOUT` (never read
upstream).

---

## 12. Commands

Upstream equivalents work today. The new repo keeps the same shape.

```bash
bash scripts/setup-dev.sh                    # hooks (commit-msg blocks attribution), once per clone

# backend — http://localhost:8000, docs at /api/docs
cd backend
poetry install                               # Python 3.12
cp .env.example .env                         # fill values locally; never commit
poetry run python main.py                    # uvicorn, reload when ENVIRONMENT=dev (main.py:225-232)
poetry run pytest -q                         # offline; no keys needed
curl -s localhost:8000/api/health/ready      # index name + guard status

# frontend — http://localhost:3000
cd frontend
npm ci
NEXT_PUBLIC_CHAT_API=http://localhost:8000 npm run dev
npm run build && npx tsc --noEmit && npm run lint

# retrieval and eval (live, billable: embeddings, rerank, LLM)
cd backend
poetry run python scripts/retrieve.py "When do instructors get paid?"   # raw + reranked, slugs/roles
poetry run python scripts/ask.py "When do instructors get paid?"        # full answer via local API
poetry run python scripts/eval_retrieval.py                             # hit@5 after rerank
poetry run python scripts/eval_answers.py                               # needs the local API running

bash scripts/upstream_diff.sh ../pathway-chatbot                        # drift of Keep/Adapt files
```

Use the **`chatbot-operator`** subagent (`.claude/agents/chatbot-operator.md`) to run, check,
and debug these.

---

## 13. Decisions and open questions

**Owner decision, 2026-10-16: every default below is accepted.** Treat the "Default" column as
decided. Q14 (real instructor questions) still needs a person to act. Reopen a row only if the
owner asks.

Why Q4 and Q5 land where they do:
- **Q4 (changed by the owner, 2026-10-16):** the instructor index is in a **separate Pinecone
  account**. The instructor bot's key therefore can't reach the missionary index at all, which is
  the strongest isolation available. The boot guard, the role/source filter, and the
  post-retrieval assertion (§7 Phase 1) stay as a second layer. They also catch a key from the
  wrong account being pasted into `.env`, because the missionary account has no
  `instructor-assistant` index to pass the guard with.
- **Q5:** separate projects keep instructor traffic, feedback, and cost out of the missionary
  dashboards. They also let access to traces that may contain student details be limited to the
  people who need it, with their own retention setting.

| # | Question | Decision (owner accepted the default, 2026-10-16) |
| --- | --- | --- |
| Q1 | Approve (a): a separate repo and deployment? | Yes. `PioneerAIAcademy/instructor-chatbot`, same visibility as pathway-chatbot (public), so §0 rule 4 matters. |
| Q2 | Does ICS need a mirror, as with the missionary bot? | No. Pioneer only until someone asks. |
| Q3 | Hosting? | Same kind of hosting as the missionary bot (Docker backend service, static frontend), as **separate** services with their own URLs. UNVERIFIED which provider hosts the missionary frontend. |
| Q4 | Should the instructor index share a Pinecone project with the missionary index? | **No: separate Pinecone account (owner, 2026-10-16).** The index already exists. Keep the guards as a second layer. Use a read-only key if the plan supports key roles (UNVERIFIED). |
| Q5 | Separate Langfuse and Sentry projects? | Yes, both. Tags as in §9 anyway. |
| Q6 | Who may use it? (Open URL + public API key, like the missionary bot, or SSO?) | Same open model. The content comes from a public site. Revisit if access to the index or the sign-in links changes. |
| Q7 | Port the agentic supervisor? | No. Classic path; Phase 10 only if the eval asks for it. |
| Q8 | Show current block and week (upstream temporal status)? | No. Only today's date. First confirm that Worldwide Online blocks use the same dates as the student academic calendar. |
| Q9 | Keep the draft composer (announcements, welcome messages)? | Yes. |
| Q10 | Dictation? | No in v1. |
| Q11 | Suggested follow-up questions? | Yes, with the instructor prompt. |
| Q12 | Languages? | English UI. Answers in the question's language (upstream behavior). Portuguese is likely needed (Brazil-based instructors, per *Pay Dates*). |
| Q13 | Include linked external pages in retrieval? | Yes, labeled external. The instructor guide wins on conflict. |
| Q14 | Who supplies real instructor questions? | The instructor support team, via the owner. Until then the §10 set stays DRAFT, and thumbs-down traces get triaged weekly once live. |
| Q15 | Is Voyage's 0.21 rerank cutoff right for this corpus? | Unchanged until Phase 2/6 data shows misses caused by it. |
| Q16 | Chat model? | `gpt-4o-mini`, as upstream. Compare `gpt-4o` on the Phase 6 set before launch if the pass rate is under target. |
| Q17 | Langfuse retention and redaction for prompts that may hold student data? | Shortest retention the plan allows. Redaction as in §9.2. |
| Q18 | Feedback screenshots (Cloudinary)? | Keep, in folder `instructor-assistant/feedback`, if the owner provides an account. Otherwise text-only feedback. |

---

## 14. Journal

Newest first. Record status, decisions, and things that failed. No secrets.

- **2026-10-19 (PR #6 review fixes, on `phase-5-observability`)** — A review of PR #6 listed 10
  findings. All 10 were checked against the code (the redaction gaps by running them) and
  fixed. `pytest tests/` gives 528 passed, keyless.
  - **Redaction gaps:** `#12345678`, `ID-12345678`, `id=12345678`, and `+1.801.555.1234` got
    through; markdown link labels weren't masked; namedtuples broke the mask.
    - Fix: one digit-run pattern; URLs cut out and kept whole; link labels masked; dates
      (2026-10-23) kept.
  - **Lost traces:** in 4.x an un-ended root is never exported.
    - `RequestTrace.finish()` now always ends the root, even if recording fails.
    - `_on_stream_end` calls `finish` in `finally`.
    - Stream end also runs from `VercelStreamResponse.__call__`, for a client that leaves
      before the body starts; `_Once` keeps it to one run.
    - Draft edit closes its trace when the rewrite raises.
  - **Late tags (`guard:audience_leak`, `outcome:*`) missed the trace:** now set on the root
    span's trace-tags attribute before it ends, plus a `tags` event.
  - **Failures counted as rerank misses:** `answer_metadata(completed=False)` sets the source
    fields to None and `answer_completed: false`, and the root is `WARNING`.
  - **Draft-edit trace input** is now what the model saw (sanitized when rated LOW).
  - **Cost counted twice:** suggestions and draft edit were generations, as is the `rag-llm`
    call under them. They're spans now.
  - **Sentry:** the event message and breadcrumbs are redacted too (`before_breadcrumb`).
  - **Docs:** §9.1 (`release` = `APP_VERSION`), §9.2 (the 4.x mask covers metadata), the status
    line, README, and `UPSTREAM.md`.
  - **Live `trace_check.py` re-run: 8/8 PASS.** It has a new check 8: a draft edit's
    `outcome:*` tag, added when the trace finishes, reaches the trace (`outcome:success`).
    The first run failed check 2 only because `APP_VERSION` wasn't set locally, and Langfuse
    drops metadata keys with no value. Run with `APP_VERSION=<git sha>`, as a build sets it,
    everything passed.

- **2026-10-19 (`.env` fixed)** — With the owner's go-ahead, the two Langfuse values in
  `backend/.env` were swapped back in place (lines 39–40, no values printed). Now
  `LANGFUSE_PUBLIC_KEY` is `pk-lf-…` and `LANGFUSE_SECRET_KEY` is `sk-lf-…`, and
  `auth_check()` is ok straight from the file. The in-memory wrapper is no longer needed.

- **2026-10-19 (Phase 5 done: Langfuse SDK 4.16.0, live check 7/7)** — Owner chose to upgrade
  the SDK. `pytest tests/` gives 514 passed, keyless.
  - **The SDK:** `langfuse` 2.60.10 → **4.16.0**, the OpenTelemetry-based SDK. 5.0.x was 3–5
    days old, a new major, and was skipped. No other package moved.
  - **The tracing model:**
    - `app/api/tracing.RequestTrace` creates the root `chat` observation in the handler and
      holds it open across the stream.
    - The orchestrator and suggestions attach via `child_kwargs()` (`langfuse_trace_id` /
      `langfuse_parent_observation_id`) inside `propagate()` (`propagate_attributes`: tags,
      user, session, trace name). `finish()` sets the output and metadata and closes the root.
    - Late tags (`guard:audience_leak`, `outcome:*`) ride on an event under the root, because
      tags only propagate to observations created inside the context.
    - Scores use `create_score`, with `score_id` as the upsert key. Draft edit and general
      feedback also use `RequestTrace`.
    - There's no per-request `flush()` any more: v4 exports in the background, and
      `main.py` flushes on shutdown.
    - Disabled-tracing IDs (all zeros) are reported as `trace_id: null`.
    - `Langfuse(environment=ENVIRONMENT, release=APP_VERSION)`.
  - **Masking:** v4's `mask` covers input, output, **and metadata**. That closes the 2.x gap.
  - **Bug found, also upstream: the LlamaIndex bridge was never attached.**
    `init_settings` checked `Settings.callback_manager is None`, but that property builds a
    default manager, so the check was never true and no `rag-llm` generation was ever
    recorded. pathway-chatbot has the same code on the same llama-index.
    - Fix: check `Settings._callback_manager`, and add the bridge if it's missing. A
      regression test checks it's on the LLM's manager.
    - The bridge now opens the generation at LLM start and ends it at LLM end.
  - **Tests can't export to Langfuse:** `conftest.py` blanks the Langfuse keys and sets
    `LANGFUSE_TRACING_ENABLED=false`. Before this, local runs loaded `.env` and tried to export
    test spans; only the swapped keys (401) kept test data out of the project. The
    draft-edit test's fake `langfuse` module was removed: with v4 it replaced the real SDK for
    every later test.
  - **Reading back (new org):**
    - Use `GET /api/public/v2/observations?traceId=…&fields=core,basic,time,io,metadata,model,usage`,
      `GET /api/public/v2/metrics` (view `observations`, dimensions `tags`/`traceName`), and
      `GET /api/public/v3/scores?traceId=…&fields=core,details`.
    - The legacy `/api/public/traces` and `/api/public/scores` (v1/v2) return **410** for
      organizations created on or after 2026-09-16.
  - **Live `scripts/trace_check.py`: 7/7 PASS.**
    - Name and §9.1 tags: on all 5 observations.
    - §9.1 metadata on the root.
    - Nesting: `retrieval-orchestrator` under `chat`, and `rag-llm` (gpt-4o-mini) under it;
      `suggestion-generation` and its `rag-llm` under `chat`.
    - A thumbs-down lands, with its comment redacted.
    - Eval tags.
    - The email and student ID masked in the root input and the rag-llm prompt.
    - No secrets in the traces or the server log.
    - Run with the keys swapped in memory (scratchpad wrapper), because `.env` still has them
      swapped.
  - **For the owner to report to pathway-chatbot:**
    1. langfuse 2.60.10 stops sending traces on 2026-11-16.
    2. The bridge was never attached, so there have never been `rag-llm` generations.

- **2026-10-19 (Phase 5 live check BLOCKED: the Langfuse SDK is too old for this org)** —
  - **`.env`:** still has the two Langfuse keys swapped. The live run used an in-memory swap
    (scratchpad wrapper), and the file is unchanged.
  - **What worked:** with the keys right, `auth_check` and `/api/health/ready` are ok
    (`status: ok`), and the SDK's ingestion POST returns 201 for every event.
  - **What failed:** nothing can be read back.
    - The SDK's `fetch_trace` (`GET /api/public/traces/{id}`) returns **410
      `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`**, and the legacy list endpoint is
      rate-limited at 5/min.
    - `GET /api/public/v2/observations` returns 200 but **0 observations** for our chat trace,
      and 0 for a probe trace sent directly with the SDK. Nothing at all in the last 2 hours.
  - **Langfuse's ingestion response says:** "On Langfuse Cloud, this is the deprecated Langfuse
    v3 ingestion API and it is shut down on **November 16, 2026**, except for score events …
    To write traces and observations, always prefer upgrading to the current Python and JS
    SDKs … The only path to live data is OpenTelemetry ingestion combined with GET
    /api/public/v2/observations …"
  - **Consequences:**
    - langfuse 2.60.10 (the §5 upstream pin) can't produce readable traces for this new
      organization, and after Nov 16 it can't send traces at all.
    - **The same applies to pathway-chatbot** (same SDK pin): its Langfuse tracing stops on
      Nov 16, except scores. Report this upstream.
  - **Decision needed (owner):** upgrade to the current OpenTelemetry-based Langfuse Python
    SDK. That reworks the `@observe` / `langfuse_context` calls, scores, the feedback trace,
    and the LlamaIndex bridge, and the masking has to be re-checked on the new SDK. The
    Phase 5 code on `phase-5-observability` (tags and metadata module, redaction, Sentry) still
    applies, but its Langfuse calls are 2.x-style.

- **2026-10-19 (Phase 5, code done; live check pending)** — Tracing and privacy per §9.
  `pytest tests/` gives 511 passed, keyless.
  - **Root cause of the Langfuse 401:** the two keys are **swapped** in `backend/.env`.
    `LANGFUSE_PUBLIC_KEY` holds the `sk-lf-…` value and `LANGFUSE_SECRET_KEY` the `pk-lf-…` one.
    The host (`https://cloud.langfuse.com`) is right. With the values swapped back, in memory
    only, `auth_check()` passed. Found without printing either key (prefix and shape checks
    only). The owner fixes `.env`.
  - **Built:**
    - `app/api/tracing.py` holds the §9.1 tags and metadata in one place:
      - tags: `app:instructor-assistant`, `role:instructor`, `index:<name>`, `feature:chat`,
        `workflow:classic`, `language:`, `security:`, plus `eval` and `eval_run:<id>` for
        `eval-` sessions;
      - metadata: `role`, `index_name`, `app_version`, `sources_core`, `sources_linked`,
        `cited_slugs`, `rerank_empty`, `login_links(_labeled)`.
    - The blocked, draft-edit, and feedback traces carry the app and role tags. The upstream
      `source:rag` tag was dropped (not in §9.1).
    - `app/redaction.py` masks emails and runs of 7+ digits (URLs, dates, and short numbers
      are untouched). It's wired into the Langfuse client and the `@observe` context.
    - The LlamaIndex bridge uses the shared masked client. It used to build a new `Langfuse()`
      on every LLM call, with no mask and its own background thread.
    - Sentry: no request bodies, no stack locals, `before_send` redaction, and
      `release=APP_VERSION`.
    - `scripts/trace_check.py` is the live Phase 5 check (7 checks, including masking and a
      secret scan of the fetched traces and the server log).

- **2026-10-19 (PR #4 review, fixed on the Phase 4 branch)** — A review of PR #4 (Phase 3)
  listed 10 findings. 4 were already fixed by the Phase 4 review round in PR #5: bold and
  code URLs, overlapping links, lazy label language, and the cached note words. The other 6
  were reproduced and fixed **on `phase-4-chat-api`**, because #4 and #5 change the same
  files. **Merge #4, then #5.** `pytest tests/` gives 492 passed. Live `api_check.py` 8/8, and
  `ask.py` on #9 and G3 ok.
  - **CJK punctuation joined URLs** (`…/x。`). Fix: bare URLs stop at any non-ASCII
    character; the guides' URLs are ASCII.
  - **Prose parentheticals counted as labels** ("(sign in to WhatsApp Web first)",
    "(Canvas login help)"). Fix: the whole note must be a localized label or a strict English
    form. §8.3 was revised. The 40-character lookahead constant was dead code (the regex is
    anchored) and is gone.
  - **Fences weren't CommonMark-style.** A one-line ```` ```x``` ```` span, or an unclosed
    fence, swallowed the rest of the answer, so later links went unlabeled and uncited.
    - Fix: `split_fences` follows CommonMark (an opening line with an optional tag, a
      closing line alone, up to 3 spaces of indent). An unclosed fence is ordinary text.
    - Citation coverage and `hoist_draft_citations` now use the same parser.
    - `draft_edit._clean_model_output` was left alone: it only unwraps the rewrite model's
      own output, not an answer.
  - **Link integrity flattened whitespace.** It collapsed every 2+ spaces in the whole
    answer, breaking list nesting, drafts, and hard breaks. Fix: it only tidies the doubled
    space where it removed a link.
  - **langdetect wasn't seeded**, so the same text could get different languages. Fix:
    `DetectorFactory.seed = 0`.
  - **A missing Voyage key slept through the retries** (about 10 s per rerank) before falling
    back. Fix: client creation fails at once, and `retrieve.prepare()` checks the key like
    `main.py` does.

- **2026-10-19 (Phase 4 review fixes)** — A review of the uncommitted Phase 4 work listed 10
  findings: 9 confirmed and fixed, 1 not an issue. `pytest tests/` gives 469 passed, keyless.
  The live `api_check.py` passes 8/8 again, and `ask.py` on #9 and G3 is ok.
  - **Shared link parser (`app/utils/links.py`):**
    - Bare URLs stop at `*` and backticks, and trailing `_`/`~` is trimmed. Before,
      `**https://…**` became the URL `…**`, which link integrity then **deleted** even though
      it was in the guide.
    - A link nested inside another (an autolink in a markdown label) is no longer found
      twice. Before, link integrity copied text twice.
  - **Annotator:**
    - A note after a citation (`[Guide](url)[^1] (sign-in required)`) counts. Before, it got
      a duplicate label.
    - A bare URL in parentheses gets its label after the `)`.
    - The label language is a function, called only when some link needs a label.
    - The note vocabulary is cached.
  - **Label language:** detected on the answer's prose only. URLs (link labels kept),
    `[^N]`, and markdown symbols are stripped first, so an English answer full of long
    SharePoint URLs no longer reads as another language.
  - **One contract module:**
    - `KEPT_ROUTES` and `client_headers()` live in `scripts/api_contract.py`.
    - `ask.py` parses with `api_contract.parse_lines` and reports stream-contract problems.
    - The OpenAPI examples in `models.py` are instructor questions now (they were
      upstream's missionary "letters" examples).
  - **Not an issue:** "the Phase 4 changes sit on `phase-3-prompt-signin`." They are on
    `phase-4-chat-api`, which was branched from Phase 3's tip and so points at the same
    commit until Phase 4 is committed.

- **2026-10-19 (Phase 4 done, branch `phase-4-chat-api`, uncommitted)** — The chat API is
  fixed and documented. `pytest tests/` gives 455 passed, keyless.
  - **Built:**
    - `backend/API.md`: headers, request body (`data.role` ignored), every error shape
      (400/401/411/413/422/429/503/500), the stream format (`0:` text, `8:` annotations
      `events`, `date_spans`, `user_language`, `sources`, `suggested_questions`, in that
      order), and the blocked-input and failed-answer streams. Also thumbs, general feedback,
      draft edit, config, and health.
    - `scripts/api_contract.py`: that stream contract as code. `tests/test_api_contract.py`
      checks it offline against the real `main.app` (only the orchestrator stubbed, 18 tests);
      `scripts/api_check.py` checks it live.
    - `/config` also splits `CONVERSATION_STARTERS` on a literal `\n`. The 4 instructor
      starters are in `.env.example`.
    - The dev `/` redirect is hidden from the schema, so `/api/docs` lists exactly the 7 kept
      routes. The dead `Result` model is removed.
  - **Live `scripts/api_check.py`: all 8 checks pass.** The stream matches API.md; source
    `url` is the guide PDF (`missionaries.prod…/<slug>`); every `[^N]` maps; G4 sources with
    `role=missionary` are identical (3 each); thumbs 200 on the trace; draft edit returns a
    rewrite; feedback 200; routes exact; 4 starters.
  - **Regression from Phase 0, found and fixed: suggested questions were broken since then.**
    `astructured_predict` imports `llama_index.agent`, which only came in through the
    `llama-index` meta-package I removed. The offline tests stub the LLM, so they never
    noticed. Fix: `llama-index-program-openai` 0.1.7 and `llama-index-agent-openai` 0.2.6
    (upstream's versions) added back. A regression test now builds the real OpenAI program.
    All 23 `llama_index` modules the app references now import cleanly.
  - **Privacy (§9.2), found in the server log during the live run:**
    - The engine's upstream `verbose=True` printed every question and every retrieved chunk
      to stdout. It's now `verbose=False`.
    - Language detection logged the first 50 characters of each question. It now logs the
      length. A test asserts a student name never reaches the log.
    - A re-run's log contains none of the request texts.
  - **Note:** the thumbs score and the feedback trace return 200, but they won't land in
    Langfuse until the 401 credentials mismatch is fixed (Phase 5).

- **2026-10-19 (Phase 3 review fixes)** — A review found 10 issues in the uncommitted Phase 3
  work. All 10 were reproduced and fixed. `pytest tests/` gives 435 passed, keyless.
  - **The backstop skipped unlabeled links.** Any nearby "sign in", "log in", or "signing"
    (it matched "signin") counted as a label. The live #9 link had passed only because the
    next sentence said "Log in…".
    - Fix: a link counts as labeled only when a **parenthesized** note follows it, in any
      supported language. §8.3 was revised.
  - **Labels landed inside link syntax.** `URL[^1]` became `URL[^1 (label)]`, and labels
    went inside autolinks and titled links.
    - Fix: one shared parser, `app/utils/links.py` (`find_links`, `split_fences`), now used
      by link integrity, the annotator, and `ask.py`.
    - Bare URLs stop before `[`, so link integrity also no longer turns `URL[^1]` into a stray
      `]`, and an invented URL no longer takes the sentence's period with it.
  - **Labels could come out in the wrong language.**
    - The prompt had the model write the English literal "(sign-in required)", which blocked
      the localized label. Now the prompt says not to write a note, and the annotator always
      adds one.
    - The label followed the request language, which can come from the settings menu. Now
      it follows the answer's detected language, falling back to the request language.
    - Labels now cover all 20 supported languages; `tl` was never shown and is gone.
  - **`login_links` counted only labels this code added** (0 when the model labeled the
    links). Fix: `login_links` = sign-in links present, `login_links_labeled` = labels added.
  - **`ask.py` checked with its own regex**, which flagged fenced drafts and missed
    ru/zh/ja/ko labels. Fix: it uses `login_links.unlabeled_login_links`.
  - **`import app.engine` needed `VOYAGE_API_KEY`** (the client was built at import). Fix:
    the client is lazy, and `main.py` refuses to boot without the key.
  - **Live re-run, 4 sign-in questions plus one in Portuguese: all checks ok.**
    - #9's course-directory link is now labeled.
    - The Portuguese answer gets "(requer login)".
    - G3 still refuses to describe the page, and cites it.

- **2026-10-19 (Phase 3 done, branch `phase-3-prompt-signin`, uncommitted)** — Final instructor
  prompt, sign-in labels, prompt lock. `pytest tests/` gives 408 passed, keyless.
  - **Built:**
    - `prompts.py` finalized from §8.1–8.2. It adds TONE, TERMS (ACL/AIM/TGL as vocabulary
      only: "facts … never from here"), LANGUAGE (answer in the question's language, Q12),
      numbered steps, and the exact label `"(sign-in required)"`, so the model and the
      annotator agree.
    - `tests/test_prompts_lock.py` pins 22 load-bearing sentences.
    - `login_links.py`: after the guards, appends the localized "(sign-in required)" to
      login-host links. It matches hosts by suffix on a domain boundary, so
      `notsharepoint.com` doesn't match. It skips a link when the text before the next link
      (up to 40 characters) already mentions sign-in or log-in, and it skips fenced drafts.
      It's idempotent. The count goes to trace metadata `login_links`. The label strings live
      in `localization.py` (`SIGN_IN_REQUIRED`).
    - `scripts/ask.py`: one question through the local API, with answer checks.
    - SharePoint link-integrity tests: a link that is inline in the guide's text survives;
      an invented one is stripped.
  - **Token budget re-measured (o200k_base):** system prompt ~820, CONTEXT_PROMPT ~160,
    retrieved contexts 1,600–2,300. That's about 3.2k at most of the 24k memory, so ~20k is
    left for history.
  - **Live check, 4 sign-in questions (§10 #9, #15, #18, G3), all CHECKS ok:**
    - **First run, G3 failed on reading.** It said the page "offers ideas and examples to
      help you create effective announcements". The guide only lists the link under
      Resources, so the model guessed from the title. It also gave no `[^N]`.
    - **Fix:** the SIGN-IN rule now says "A link's title is not a description", "If the guide
      only lists the link … say that the guide links to it, and nothing more about its
      content", and "cite the guide it came from with [^N]".
    - **Re-run:** G3 says the page is behind a sign-in, gives the link with the label, and
      cites [^1], with no content guessing.
    - #9's course-directory link has no added label, correctly: the next step says "Log in
      using your BYU-Idaho email and credentials".
    - #15 and #18 surfaced no sign-in links (their guides have 11 and 10).
  - **Flaky-test cause found (from the Phase 1 note):** `/api/v1/chat`'s real
    `10/minute` limiter is process-wide. `test_chat_api.py` crossed 10 requests per minute
    only when the timing was tight, which gave an intermittent 429. Fix: the fixture calls
    `limiter.reset()` for each test (3 repeat runs clean).
  - **Found, not fixed:**
    - **Other hosts that may need a sign-in.** `forms.office.com` (12 links),
      `customervoice.microsoft.com` (14), `docs.google.com` (17), and `video.byui.edu` (11)
      appear in the guides. Whether they need a sign-in is unverified, and adding a host to
      `LOGIN_LINK_HOSTS` is an owner decision.
    - **Repeated lines in a merged context.** The WhatsApp community guide's context repeats
      "Click on the Communities icon…" several times. That looks like overlapping chunks
      concatenated by `_merge_nodes_with_headers`. Check it in Phase 6, if answers suffer.

- **2026-10-19 (Phase 2 review fixes)** — A review found 10 issues across the merged Phase 1
  code and the uncommitted Phase 2 eval. All 10 were confirmed and fixed. `pytest tests/` gives
  350 passed, keyless. The branch was fast-forwarded onto `main` after PR #2 merged.
  - **The eval could pass with no rerank measured.** A failed Voyage rerank falls back to raw
    order, but failures weren't part of `passed`.
    - Fix: any rerank failure, or any errored question, now fails the run.
    - Errors are recorded per question, so a timeout on question 18 no longer throws away the
      17 paid results before it.
  - **Miss attribution was too loose.** Any miss whose doc appeared anywhere in the raw top
    35 was blamed on rerank.
    - Fix: misses now split into `lost_in_rerank` (in the raw top 5 and pushed out),
      `not_lifted` (raw rank 6–35), `not_retrieved`, `rerank_failed`, and `error`. Q15
      decisions need this split.
  - **Phrase matching was substring-based, so it misfired.** "ACM" matched "Macmillan", "ID"
    matched "guide", "I read" matched "AI readiness".
    - Fix: `evalset.contains_phrase` matches whole words, case-insensitively; a trailing `*`
      makes a prefix.
    - Bare "gathering" was dropped from `defaults.must_not` ("start by gathering the facts" is
      fine). The specific terms took its place: `missionar*`, `gathering agenda*`,
      `My Gatherings`, `ACM(s)`, and `I read/checked/opened/reviewed`.
    - **Deviation from §7 Phase 6 check 5:** "Student Portal as an instructor action" needs
      judgment, not a phrase, so it's left to the Phase 6 LLM judge.
  - **Disconnect race in Phase 1 code.** On a client disconnect, the stream read
    `audience_leak_dropped` before the cancelled `run()` reached its `finally`, so a leak was
    lost.
    - Fix: the orchestrator holds the guard, and the count is a live property.
  - **Readiness could block the event loop.** It built the store on the loop, so a cold
    control-plane lookup stalled every stream.
    - Fix: the whole check runs in `asyncio.to_thread`.
  - **Small fixes:**
    - One audience rule, `audience_guard.is_instructor_metadata`, used by the guard and the
      eval.
    - `retrieve.py --expect` uses the eval's matching (case-insensitive slugs, URLs).
    - Setup (`prepare()`) runs once per eval run. A fresh engine per question stays on
      purpose, because it owns that question's guard counter.
    - `document_rank` is a single pass.
  - **Re-run, `20261019T072427Z-retrieval.json`:** the same 20/21 = 95%, PASSED, under the
    stricter rules. 0 rerank failures, 0 errors. #4 is attributed `lost_in_rerank`.

- **2026-10-19 (Phase 2 done, branch `phase-2-retrieval-eval`, uncommitted)** — The retrieval
  eval runs the §10 questions through the production retriever plus rerank.
  - **Built:**
    - `tests/eval/questions.yaml`: the §10 set (21 + G1–G4) with `expect`/`expect_url`,
      `must_include` groups, `defaults.must_not`, G4's `data.role` and `same_as`. Still DRAFT
      (Q14). Every `expect` slug was checked against the indexer's
      `data/state.json` (72 docs = 33 PDFs + 39 linked pages); all exist.
    - `scripts/evalset.py`: loader and scoring, shared with Phase 6.
    - `scripts/eval_retrieval.py`: the eval. Results in `tests/eval/results/` (gitignored).
    - `pyyaml` listed explicitly. 329 tests pass offline.
  - **Decision: hit@5 means the indexer's rule.** An expected document must appear in the top
    5 *chunks*, matched by slug or normalized URL (instructor-indexer
    `verify._hit_rank`/`_normal_url`). The eval also reports the document-level rank, and the
    rank before rerank so a miss can be blamed on rerank or on retrieval.
  - **Result, `20261019T070247Z-retrieval.json` (index `instructor-assistant`,
    rerank-lite-1, top 17, ≥ 0.21): hit@5 20/21 = 95%, target 90%. PASSED.** 0 empty
    contexts, 0 non-instructor nodes, 0 rerank failures. 18 of the 20 hits are at rank 1;
    #13 is at 3 and #21 (linked page) at 2.
  - **The one miss, #4** ("give just one student more time on an assignment in Canvas"):
    - The guide ranked 1st before rerank and 7th after (3rd by document).
    - 7 of its 9 retrieved chunks were kept, at Voyage scores 0.66–0.70. The top 5 were the
      Accessibility guide (0.78, 0.70) and the Canvas "timed quiz" linked page (0.77,
      0.73, 0.70). "More time" reads like an extra-time accommodation.
    - **Not the 0.21 cutoff** (the 2 chunks that fell out lost to the top-17 limit, not the
      threshold), and 7 of the guide's chunks still reach the model as context.
      Per Q15 the threshold is unchanged; Phase 6 shows whether the answer suffers.

- **2026-10-18 (Phase 1 review fixes, PR #2)** — A review of PR #2 found 9 issues. All 9 were
  checked against the code and fixed. `pytest tests/` gives 310 passed, keyless. The live
  re-run matched the first one exactly (rank 1 for all 5, nothing dropped).
  - **The script copied the rerank logic, and it drifted.** `retrieve.py` sent Voyage an
    empty list, raised on a Voyage failure, and applied the cutoff with one text, in each
    case unlike production.
    - Fix: one `rerank_nodes()` in `custom_condense_plus_context.py`, used by both engine
      paths and the script.
    - It skips the rerank at ≤ 1 unique text, and keeps every text unranked when Voyage fails.
    - Dedup now preserves order. Upstream's `set()` made the failure fallback order random.
    - The script prints the real `RERANK_MIN_SCORE` and reports a skipped or failed rerank
      the way production handles it.
  - **Lost leaks:** a leak was lost when synthesis failed.
    - Fix: the orchestrator records `audience_leak_dropped` on itself in a `finally`.
      `chat.py` keeps the instance and tags the trace in `_on_stream_end`, which always runs.
  - **Fragile guard lookup:** the guard was found by digging through the private
    `_node_postprocessors`.
    - Fix: `get_chat_engine()` sets a public `engine.audience_guard`.
    - The orchestrator **fails closed**: an engine without its guard raises before
      retrieving.
    - The repeated Langfuse ERROR blocks became one `_mark_observation_error()`.
  - **Only the exact name `pathway` was denied.**
    - Fix: also `pathway-*`, `pathway_*`, and any name containing "missionar", even if
      allow-listed.
    - The allow-list and the separate account are still the real controls.
  - **Index check on every request:** `check_index_config` ran on every
    `get_vector_store()` call.
    - Fix: it moved into `_build_store()`, so it runs on cache misses only. The cache key
      includes the index name, so nothing is lost.
  - **Readiness tested the wrong path:** it probed the control plane while requests use the
    host.
    - Fix: a data-plane `describe_index_stats` through the request client. Stats are never
      returned.
  - **Flaky test, cause not proven.** 1 failure in 5 full-suite runs, not reproduced in 4
    more full runs or 6 targeted runs. I lost the trace, because I filtered the output
    without `-rf`. The most likely cause is the security tests' Hugging Face request on
    every validator call (the pytector finding).
    - Fix: `conftest.py` sets `HF_HUB_OFFLINE`, which takes the suite off the network.
      Suite time went from about 180 s to about 92 s.
    - If it recurs, run with `-rf` and record the test name here.

- **2026-10-18 (Phase 1 done, branch `phase-1-audience-guard`, uncommitted)** — Audience lock
  and index switch. `pytest tests/` gives 286 passed, keyless.
  - **Built:**
    - `audience_guard.check_index_config()` runs at boot (`main.py`), in
      `get_vector_store()`, and in `/api/health/ready`. It refuses a name not in
      `ALLOWED_INDEX_NAMES`. It always refuses `pathway`, even if someone allow-lists it. And it
      refuses a `PINECONE_INDEX_HOST` that isn't the named index's host.
    - `AudienceGuardPostprocessor` runs first among the engine's postprocessors and drops
      wrong role/source nodes (`ERROR audience_leak`). The count reaches the trace as tag
      `guard:audience_leak` plus metadata `audience_leak_dropped`, and the orchestrator span
      is marked ERROR.
    - `/api/health/ready` now returns `{status, index, guard}`, and skips the Pinecone call
      when the guard refuses the config.
    - `scripts/retrieve.py`: raw top 35 and reranked top 17, with slug, source, role, score.
      `--expect <slug>` exits 1 if the slug isn't in the top 5. Rerank settings are now
      module constants in `custom_condense_plus_context.py`, so the script can't drift from
      production.
  - **Decision: the host check parses, it doesn't prefix-match.** §7's "starts with
    `<name>-`" would accept `instructor-assistant-staging-…` for `instructor-assistant`. §5
    updated.
  - **Done-when:**
    - Offline: unit tests cover the same filter for client `role` ∈ {absent, missionary, ACM,
      instructor, garbage} (through the API); boot refusing `pathway` and a mismatched host
      (in a subprocess running `import main`); and the assertion dropping a planted
      `role=missionary` node.
    - Live, 5 questions (§10 #1, #3, #5, #7, #10): every raw node `role=instructor` from
      `instructor-assistant[-linked]`, 0 dropped, and the expected slug **rank 1** after
      rerank for all 5 (top scores 0.68–0.91).
    - Live: the same 5 with `PINECONE_INDEX_NAME=pathway` exit 1 with `IndexConfigError`
      before any Pinecone client is built, and so does `import main`.
  - **§5 reader pins confirmed live:** `vector-stores-pinecone 0.1.9` reads the nodes the
    indexer wrote with 0.1.3 (text, `slug`, `role`, `source`, `url` all present).
  - **Guard findings in upstream test data:** `test_vectordb_client.py` used
    `PINECONE_INDEX_NAME="pathway"` and a `pathway-…` host. The fixtures now use the
    instructor index; the guard wasn't changed.
  - **Phase 0 regression fixed:** `package-mode = false` meant `scripts/*.py` couldn't
    `import app`. `sec_test.py` and `retrieve.py` now put `backend/` on `sys.path`.
  - **Finding (Phase 5):** `/api/health/ready` reports Langfuse `401 Invalid credentials.
    Confirm that you've configured the correct host`. All three `LANGFUSE_*` variables are
    set, so the keys and `LANGFUSE_HOST` don't match (wrong region host, or keys from another
    project). Readiness shows `degraded` until that's fixed.

- **2026-10-17 (Phase 0 review fixes, still uncommitted)** — A code review of the scaffold found
  10 issues. All 10 were checked against the code (and against the installed llama-index for
  the library claims) and fixed. `pytest tests/` gives 248 passed, keyless. Details are in
  the `UPSTREAM.md` rows.
  - **Draft fences broke:** `ensure_citation_coverage` stamped `[^1]` on the ```` ```message ````
    fence line and inside drafts.
    - Fix: coverage now skips fenced blocks.
    - New `hoist_draft_citations()` moves markers the model put inside a draft fence to just
      after it.
  - **Handler leak and cross-talk:** each request appended its `EventCallbackHandler` to the
    global `Settings.callback_manager`.
    - Fix: a per-request CallbackManager on the engine and its retriever.
    - LLM-stage status events no longer reach the stream. The LLM is shared, so they only
      go to Langfuse.
    - **Upstream has the same leak.**
  - **Blank answers:** a failed OpenAI stream was swallowed and shipped as a blank answer
    with sources.
    - Fix: `SynthesisFailedError` (also raised for an empty draft), the Langfuse observation
      marked ERROR, and the localized hiccup text in the stream.
    - Any stream exception now shows the hiccup text, not `str(exc)`.
  - **Fake citations on refusals:** coverage stamped `[^1]` on refusals and caveats.
    - Fix: a wholly uncited answer is left alone, and more English caveat openers are exempt.
    - **Behavior change from upstream.** An answer where the model cited nothing now shows
      no citations, where it used to show a made-up `[^1]`. Phase 6 check 1 will surface
      those as failures. Caveats in other languages inside a cited answer can still pick up
      a marker.
  - **Forged history roles:** client history could carry `system`/`tool` turns.
    - Fix: only `user`/`assistant`, and the last message must be `user` (otherwise 422).
    - **Residual:** forged `assistant` turns are still possible. The API is stateless and
      only the last message is screened; that's the same as upstream.
  - **Dropped drafts went unannounced:** a screened-out edited draft was dropped silently.
    - Fix: `build_dropped_draft_notice()` tells the model it can't see the edits.
  - **Wrong language:** language detection ran on the message after the English draft
    scaffolding was appended.
    - Fix: answer language and indicator language come from the typed text.
  - **CI Poetry:** Poetry 1.8.2 in CI reads the 2.1 lock but warns "might not be
    compatible".
    - Checked: `poetry check --lock` and a dry-run install both work with 1.8.2, and
      upstream gets the same warning.
    - Fix: CI pinned to Poetry 2.4.1.
  - **Dead docs redirect:** the dev `/` redirect pointed at `/docs`, a 404. Fix: `/api/docs`.
  - **Upload annotations leaked into prompts:** `document_file` annotations were still
    merged in, because the `if not filter(...)` check never fires.
    - Fix: `get_last_message_content` returns only the last message.
  - New tests: `tests/test_chat_api.py`, plus cases in `test_grounding_guard.py`,
    `test_draft_normalizer.py`, and `test_retrieval_orchestrator.py`.

- **2026-10-17 (Phase 0 done, branch `phase-0-scaffold`, uncommitted)** — Backend scaffold copied
  from pathway-chatbot `870cc5b` and trimmed. File-by-file record in `UPSTREAM.md`;
  `scripts/upstream_diff.sh ../pathway-chatbot` shows upstream drift (0 of 67 files today).
  - **Done-when, all met:**
    - `pytest tests/` gives 230 passed in a clean copy (tracked + committable files only, no
      `.env`, empty environment), using Python 3.12.13.
    - The commit-msg hook exits 1 on a `Co-Authored-By` line and 0 on a clean message;
      `core.hooksPath = .githooks` is set on this clone.
    - `grep -rniE 'tuition|calendar|agenda|ACM' backend/app` hits only the four intentional
      places listed in `UPSTREAM.md`.
    - The app imports with placeholder keys and serves only `/api/v1/chat` (+ `/draft/edit`,
      `/thumbs_request`, `/feedback/general`, `/config`) and `/api/health[/ready]`.
  - **Pulled forward from later phases, to keep missionary behavior out of the scaffold:**
    - `audience_guard.instructor_filters()` (Phase 1 part): `role == instructor` AND
      `source in RETRIEVAL_SOURCES`; `chat.py` ignores `data.role`.
    - `prompts.py` with the §8.2 draft (Phase 3 finalizes it and adds the lock test).
    - The instructor source label in `custom_condense_plus_context.py` (§4 Adapt).
    - Classic `RetrievalOrchestrator`: drain, then grounding guards.
    - `chat.py` trimmed to 751 lines (not the ~300 in §4). Draft edit, thumbs, and feedback
      alone are ~400.
    - Instructor prompts for suggestions and draft edit.
  - **Still to do in Phase 1:** the index/host boot guard, the post-retrieval role assertion,
    `/api/health/ready` index + guard fields, `scripts/retrieve.py`, and the rest of
    `test_audience_guard.py`.
  - **Deps:** the `llama-index` meta-package was replaced by core + llms-openai +
    embeddings-openai + vector-stores-pinecone, at the same locked versions (0.10.58 / 0.1.27 /
    0.1.11 / 0.1.9; pinecone-client 5.0.1, langfuse 2.60.10). The lock went from 270 to 125
    packages. llama-cloud, spacy, arize-phoenix, and jupyterlab are gone.
  - **Finding (inherited from upstream, not fixed): the pytector ML injection detector never
    loads.** `transformers 5.3.0` requires torch ≥ 2.4, but torch is pinned to 2.2.2, so
    `PromptInjectionDetector()` raises and `get_pytector_detector()` returns `None`. Only the
    regex checks run. The `None` isn't cached, so every validated message retries the load (a
    Hugging Face Hub request each time). pathway-chatbot has the same lock, so the missionary
    bot is most likely affected too. torch 2.2.2 is the last release with macOS x86_64 wheels,
    which may be why it's pinned. Fixing it is an owner decision (upgrade torch, or pin
    transformers < 5), and the security corpus must be re-run afterwards
    (`scripts/sec_test.py`).
  - **Resolved UNVERIFIED (§4):** `date_spans` isn't calendar-only. The frontend's
    `markdown.tsx` highlights those phrases in every answer's paragraphs, so it's kept.
  - **Left alone on purpose:** `input_validator.py` is byte-identical, including the
    missionary allowlist terms. Adding instructor terms (§4 Adapt) has to come with a
    security-corpus re-run.
  - Local env note: Poetry 2.4.1 and uv's CPython 3.12.13. The poetry venv is
    `app-91BJ_1qn-py3.12`.

- **2026-10-17 (backend first)** — Owner: build the backend before the frontend. §7 is now split:
  - **Part A, backend, Phases 0–7.** The scaffold has no `frontend/`. Phase 4 is the chat API
    alone, checked with `curl`/`ask.py`, and writes `backend/API.md` as the contract. Phase 7 is
    the backend staging deploy and the "Backend done" gate.
  - **Part B, frontend, Phases 8–9.** Phase 8 is the frontend; Phase 9 is end-to-end and
    production.
  - The optional agentic phase moved from 8 to 10.

- **2026-10-16 (Pinecone account)** — Owner: the `instructor-assistant` index already exists, and
  the Instructor Assistant uses a **separate Pinecone account** from the missionary bot. This
  replaces the "same project" assumption from indexer Q2 (§1, §11, §13 Q4 updated). The guards
  stay as a second layer.

- **2026-10-16 (decisions)** — Owner accepted every §13 default (Q1–Q18): separate public repo
  `PioneerAIAcademy/instructor-chatbot`, no ICS mirror, separate Langfuse and Sentry projects, open access, classic RAG path, no
  block status, English UI. Next: move this folder into the new repo, then Phase 0.

- **2026-10-16 (plan written, no code)** — Read pathway-chatbot `main` @ `870cc5b` end to end
  (frontend → `/api/v1/chat` → filters → retrieval → rerank → prompt → guards → stream →
  citations → Langfuse) and instructor-indexer `main` @ `2436a34` (§1, §5, §8, journal).
  - **Decision: (a) separate repo and deployment** (§3), with the classic RAG path for v1.
  - Findings that shaped the plan:
    - The role is chosen by the client and unknown roles fall back to `missionary`.
    - The API key is public.
    - `PINECONE_INDEX_HOST` overrides the index name.
    - `SYSTEM_PROMPT` env is never read.
    - With no `vintage_year` in the index, the supervisor's `target_year` filter would return
      zero results.
    - Starter questions never render upstream.
    - Linked pages also carry `role=instructor`.
    - SharePoint links survive link integrity because their URLs are in the node text.
  - Eval set drafted (21 + 4 guards, DRAFT).
  - Next: owner answers Q1–Q6, then Phase 0.
