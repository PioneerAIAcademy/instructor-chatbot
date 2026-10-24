# Upstream provenance

This repo was copied and trimmed from
[`PioneerAIAcademy/pathway-chatbot`](https://github.com/PioneerAIAcademy/pathway-chatbot)
(the Missionary Assistant). Fixes do not flow between the two automatically.
This file lists every file that came from upstream, so drift can be checked.

- **Upstream base commit:** `870cc5b` (pathway-chatbot `main`, 2026-10-05)
- **Copied in:** Phase 0, 2026-10-17
- **Check drift:** `bash scripts/upstream_diff.sh ../pathway-chatbot` prints what changed
  upstream in each file below since the base commit. It's read-only and uses only the local
  checkout (run `git -C ../pathway-chatbot fetch` first if you want the newest `main`).

Status:
- **Keep** means copied byte-for-byte.
- **Keep\*** means copied with small edits.
- **Adapt** means copied, then reworked.

`scripts/upstream_diff.sh` reads the table rows below (the two path columns), so keep
them in this shape.

## Files

| Local path | Upstream path | Status | Local changes |
| --- | --- | --- | --- |
| `.githooks/commit-msg` | `.githooks/commit-msg` | Keep\* | Rule references point to CLAUDE.md §0 rule 1. |
| `.githooks/post-commit` | `.githooks/post-commit` | Keep | — |
| `.githooks/pre-push` | `.githooks/pre-push` | Keep\* | Frontend `tsc`/`lint` restored in Phase 8; skipped when `frontend/node_modules` is absent. |
| `.githooks/README.md` | `.githooks/README.md` | Keep\* | Lists all three hooks; activation via `setup-dev.sh`. |
| `.github/workflows/payload-guard.yml` | `.github/workflows/payload-guard.yml` | Keep | — |
| `.github/workflows/test.yml` | `.github/workflows/test.yml` | Keep\* | Poetry 2.4.1 (the version that wrote `poetry.lock`) instead of 1.8.2. Phase 7 adds a `docker` job: builds the image and checks no `.env` inside, non-root, `ENVIRONMENT=prod`, the boot guard refusing `pathway`, 401 without a key, CORS locked, JSON logs. Phase 8 adds a `frontend` job: build, `tsc`, lint, no missionary terms, and an image holding only `out/`. |
| `scripts/setup-dev.sh` | `scripts/setup-dev.sh` | Keep\* | Rule and context references point to CLAUDE.md. |
| `docs/agent-onboarding/journal-skill/SKILL.md` | `docs/agent-onboarding/journal-skill/SKILL.md` | Keep\* | CLAUDE.md is committed here, so it must never hold secrets. |
| `.gitignore` | `.gitignore` | Adapt | Rewritten. `.claude/agents/` stays tracked. |
| `backend/.gitignore` | `backend/.gitignore` | Keep\* | Tuition/calendar data lines dropped; `tests/eval/results/` added. |
| `backend/Dockerfile` | `backend/Dockerfile` | Keep\* | Stale comments (web loader, spacy) removed. Phase 7: an allow-list `.dockerignore` (upstream has none, so `COPY . .` copied a local `.env` into the image); gunicorn binds `0.0.0.0:${PORT:-8000}` (upstream binds 127.0.0.1 unless the host sets `PORT`); Poetry pinned to 2.4.1; `ENV ENVIRONMENT=prod`; `APP_VERSION` build arg. |
| `backend/pyproject.toml` | `backend/pyproject.toml` | Adapt | `llama-index` meta-package replaced by the four parts the chat path imports (same locked versions). Dropped: spacy, llama-cloud, arize-phoenix, pandas/pyarrow/boto3/apscheduler, docx2txt, jupyterlab, unused security pins. `pyyaml` listed explicitly for the eval set (it was already locked at 6.0.3 as a transitive dependency). `langfuse` is 4.16.0 (Phase 5; upstream's 2.60.10 uses the ingestion API Langfuse Cloud shuts down on 2026-11-16). `llama-index-program-openai` 0.1.7 and `llama-index-agent-openai` 0.2.6 restored in Phase 4 (upstream's versions): suggested questions' `astructured_predict` needs them, and the Phase 0 trim had silently broken it. Pre-deploy: `transformers` pinned to 4.57.1 (5.x needs torch ≥ 2.4; torch stays 2.2.2, the last build for Intel Macs). |
| `backend/poetry.lock` | `backend/poetry.lock` | Adapt | Re-locked with `poetry lock` (Poetry 2.4.1, which keeps existing versions); 270 → 125 packages. Every remaining package kept its upstream-locked version. Pre-deploy: re-locked for transformers 4.57.1 (huggingface-hub 1.16.1 → 0.36.2; six CLI-only packages dropped). |
| `backend/main.py` | `backend/main.py` | Adapt | Boot runs `check_index_config()` and refuses a wrong index or host, and refuses a missing `VOYAGE_API_KEY`. Only chat, config, health routers. No calendar/tuition/dictation/upload routers, file server, block-date or tuition schedulers, or S3 monitoring scheduler. The dev root redirect goes to `/api/docs` (upstream pointed at `/docs`, a 404) and is hidden from the API schema. Sentry: no request bodies, no stack locals, `release` = `APP_VERSION`, and `before_send` / `before_breadcrumb` redact exception values, messages, log entries, and breadcrumbs. Shutdown flushes Langfuse. Pre-deploy: preloads the injection model in a background thread at startup. `ALLOWED_ORIGINS` entries are compared without a trailing slash (browsers never send one, so `https://site/` blocked every request). With `ENVIRONMENT=dev` set explicitly, any `http://localhost` / `127.0.0.1` port is also allowed (`next dev` moves to :3001 when :3000 is taken); never in prod or when `ENVIRONMENT` is unset. |
| `backend/app/__init__.py` | `backend/app/__init__.py` | Keep | — |
| `backend/app/auth.py` | `backend/app/auth.py` | Keep | — |
| `backend/app/langfuse.py` | `backend/app/langfuse.py` | Adapt | langfuse 4.x client with `mask` (input, output, metadata), `environment`, and `release`. `real_id()` maps disabled-tracing (all-zero) IDs to None. |
| `backend/app/observability.py` | `backend/app/observability.py` | Keep | — |
| `backend/app/http_client.py` | `backend/app/http_client.py` | Keep | — |
| `backend/app/memory_trim.py` | `backend/app/memory_trim.py` | Keep | — |
| `backend/app/settings.py` | `backend/app/settings.py` | Keep\* | OpenAI provider only (llmhub and the other providers dropped). The LlamaIndex Langfuse bridge is actually attached: upstream checked `Settings.callback_manager is None`, which is never true (the property builds a default), so it never was. |
| `backend/app/security/__init__.py` | `backend/app/security/__init__.py` | Keep | — |
| `backend/app/security/input_validator.py` | `backend/app/security/input_validator.py` | Adapt | Phase 7: `INSTRUCTOR_TERMS` (instructor, adjunct, ACL, AIM, TGL, FERPA, block, syllabus, WhatsApp, extension, grade…), matched as whole words, join the allowlist that excuses an ML-only (pytector) MEDIUM flag. Never a pattern hit. `scripts/sec_test.py` gives identical per-case results before and after (29/32, the same 3 known gaps). Has no effect until pytector loads (Phase 0 finding). The missionary terms are still in `PATHWAY_TERMS`. Pre-deploy (2026-10-20): the ML detector works (it never loaded upstream: transformers 5 needs torch ≥ 2.4); it loads once under a lock, preloads at startup, backs off 10 min after a failed load, runs in a worker thread, and can be turned off (`PROMPT_INJECTION_ML_ENABLED`). Upstream's `CALENDAR_TERMS` and `PATHWAY_TERMS` removed; the short-follow-up exception refuses text about the assistant itself. Security corpus with the detector on: 30/32 (was 29/32 with regex only). |
| `backend/app/middleware/monitoring_middleware.py` | `backend/app/middleware/monitoring_middleware.py` | Keep\* | S3 metrics-collector calls (`app.monitoring`, not ported) removed. Request IDs, 499 on disconnect, and crash logging unchanged. |
| `backend/app/utils/langfuse_llama_index.py` | `backend/app/utils/langfuse_llama_index.py` | Adapt | langfuse 4.x: the `rag-llm` generation starts at LLM start (a child of the active span) and ends at LLM end, on the shared masked client. |
| `backend/app/utils/localization.py` | `backend/app/utils/localization.py` | Keep\* | Agenda-not-found and missionary site-index strings, and the geo country map, removed. `SIGN_IN_REQUIRED` label added for all 20 supported languages (en + 19 LLM translations, pending native review). Language detection logs the language and the text's length, not its first 50 characters (questions may name students; §9.2). langdetect is seeded (`DetectorFactory.seed = 0`), so detection is deterministic. |
| `backend/app/utils/date_spans.py` | `backend/app/utils/date_spans.py` | Keep | Feeds the frontend's date highlighting in any answer, so it isn't calendar-only. |
| `backend/app/api/__init__.py` | `backend/app/api/__init__.py` | Keep | — |
| `backend/app/api/routers/__init__.py` | `backend/app/api/routers/__init__.py` | Keep | — |
| `backend/app/api/routers/chat.py` | `backend/app/api/routers/chat.py` | Adapt | Rewritten around the classic path. Passes the reply language to the orchestrator and records `login_links` in trace metadata. Language is resolved from the typed message, before the edited-draft block is appended. A screened-out edited draft adds a notice telling the model it can't see the edits. Ignores `data.role` (warns if it isn't `instructor`). Filter is `instructor_filters()`. No geo lookup, agenda scope, widget router, calendar/tuition, supervisor, ACM prefix, or `/request`. Draft edit, thumbs, and general feedback kept. Cloudinary folder `instructor-assistant/feedback`. `role:instructor` tag on draft-edit and feedback traces. `_resolve_language` also reports whether the settings pick decided the language; then the orchestrator passes `answer_language` and the system prompt names it. |
| `backend/app/api/routers/chat_config.py` | `backend/app/api/routers/chat_config.py` | Adapt | Unset `CONVERSATION_STARTERS` serves the 4 built-in instructor cards (`DEFAULT_STARTERS`, `Title \| question`); set but blank serves none. LlamaCloud route removed. `CONVERSATION_STARTERS` also splits on a literal `\n` (hosting dashboards can't store real newlines). `?lang=` serves the built-in cards in Spanish or Portuguese; `CONVERSATION_STARTERS_ES` / `_PT` override them. |
| `backend/app/api/routers/events.py` | `backend/app/api/routers/events.py` | Keep | — |
| `backend/app/api/routers/health.py` | `backend/app/api/routers/health.py` | Keep\* | `/health/ready` also returns `index` and `guard`. The Pinecone check is a data-plane `describe_index_stats` through the same cached client requests use (so a set `PINECONE_INDEX_HOST` is what gets tested), instead of a control-plane `describe_index`. The whole check, including building the store, runs in a thread, so a cold control-plane lookup can't block the event loop. It's skipped when the guard refuses the config. |
| `backend/app/api/routers/message_variations.py` | `backend/app/api/routers/message_variations.py` | Keep\* | Calendar, graduation, pushback, and text-format status pools removed. |
| `backend/app/api/routers/models.py` | `backend/app/api/routers/models.py` | Adapt | File-server URL rewrite and `DATA_DIR` import removed. Client messages may only be `user`/`assistant`, and the last must be `user`. `get_last_message_content` no longer merges `document_file` annotations into the prompt (upstream's `if not filter(...)` check never fired). `get_chat_document_ids` and the `Result` model (for the removed `/request` route) removed. |
| `backend/app/api/routers/vercel_response.py` | `backend/app/api/routers/vercel_response.py` | Adapt | Calendar paths, supervisor emit queue, stream-first correction, and prebuilt annotations removed. Streams text, `events`, `date_spans`, `user_language`, `sources`, `suggested_questions`. Any answer failure (not only a hang) streams the localized hiccup text; upstream sent `str(exc)` as a `3:` error. Stream end runs exactly once (`_Once`), and also from `__call__` when the client leaves before the body starts, so the request's trace always closes. |
| `backend/app/api/services/draft_edit.py` | `backend/app/api/services/draft_edit.py` | Keep\* | Persona is the Instructor Assistant; the students/learners terminology line dropped. The rewrite is an `@observe` span, not a generation (the `rag-llm` bridge already records the LLM call and its cost). |
| `backend/app/api/services/suggestion.py` | `backend/app/api/services/suggestion.py` | Keep\* | Prompt rewritten for instructors (first person, "students"). A span, not a generation, for the same reason as draft edit. |
| `backend/app/engine/__init__.py` | `backend/app/engine/__init__.py` | Adapt | `verbose=False` (upstream: True, which printed every question and retrieved chunk to stdout; §9.2). `AudienceGuardPostprocessor` runs first among the postprocessors. Same wiring (top_k 35, sparse 175, 24K memory). Prompts come from `prompts.py`. No temporal status, tuition facts, or program ladder. |
| `backend/app/engine/vectordb.py` | `backend/app/engine/vectordb.py` | Keep\* | `_build_store()` calls `check_index_config(index_name, PINECONE_INDEX_HOST)` before building a client, which closes the host-overrides-name path. Cache hits skip it: the cache key includes the index name, so a cached store already passed. |
| `backend/app/engine/index.py` | `backend/app/engine/index.py` | Keep | — |
| `backend/app/engine/node_postprocessors.py` | `backend/app/engine/node_postprocessors.py` | Keep | — |
| `backend/app/engine/custom_node_with_score.py` | `backend/app/engine/custom_node_with_score.py` | Keep | — |
| `backend/app/engine/custom_condense_plus_context.py` | `backend/app/engine/custom_condense_plus_context.py` | Keep\* | `audience_marker` replaced by `source_label` (instructor guide vs external page). `clean_retrieved_text` (missionary-corpus rules) dropped. The rerank rules are extracted into one module-level `rerank_nodes()` (same model, top-k, 0.21 cutoff, the "skip when ≤ 1 unique text" rule, and the "keep unranked on Voyage failure" fallback), used by `_organize_nodes`, `_aorganize_nodes`, and `scripts/retrieve.py`. Dedup is now order-preserving (upstream's `set()` made the fallback order random). The grouping/merge step is one `_group_and_merge` instead of two copies. `audience_guard` class attribute added. Upstream's debug `print()`s of every node's text in the sync `_retrieve_context` removed. The Voyage client is created on first use instead of at import (a missing key fails at once, without the retry sleeps), so importing `app.engine` doesn't need `VOYAGE_API_KEY` (`main.py` still refuses to boot without it). Phase 6: external-page labels name the owner ("external page from BYU-Pathway (host)") via `SITE_OWNERS`. |
| `backend/app/engine/grounding_guard.py` | `backend/app/engine/grounding_guard.py` | Keep\* | Link integrity and fence detection use the shared parser in `app/utils/links.py` (also used by the sign-in annotator): bare URLs stop before `[`, so `URL[^1]` keeps its citation, and titled links and autolinks are handled. An invented bare URL is dropped without eating the sentence's period, and only the doubled space at that seam is tidied (upstream collapsed every 2+ spaces in the answer, breaking list nesting and drafts). Coverage uses the shared CommonMark-style fence parser. `ensure_citation_coverage` skips fenced blocks (and their fence lines) and wholly uncited answers. More English caveat/refusal openers are exempt. Docstrings still describe upstream's agentic loop. Phase 6: `normalize_citation_markers()` runs first, repairing `[^1^]`/`[^ 1]` and dropping a literal `[^N]`. Pre-deploy: citation coverage stamps the nearest real citation (not a blanket `[^1]`) and skips lead-in lines ending in ":". |
| `backend/app/engine/retrieval_orchestrator.py` | `backend/app/engine/retrieval_orchestrator.py` | Adapt | Classic engine, then drain, then `apply_grounding_guards`, then `hoist_draft_citations`. No recency engine or critic. Then `annotate_login_links` labels sign-in links (§8.3) in the reply language; its count is `login_links`. A guard failure ships the unguarded draft. A failed or empty answer stream raises `SynthesisFailedError`. `audience_leak_dropped` reads the guard's live counter, so it's right even when a client disconnect cancels `run()` before its cleanup. The per-request `EventCallbackHandler` goes on a per-request CallbackManager; upstream appends it to the global `Settings.callback_manager`, which leaks handlers and mixes status events across requests. Phase 6: `tag_untagged_drafts()` runs before `hoist_draft_citations()`. |
| `backend/app/engine/draft_context.py` | `backend/app/engine/draft_context.py` | Keep\* | `build_dropped_draft_notice()` added. Upstream's `chat.py` comment promised to tell the model, but it only logged. |
| `backend/app/engine/draft_normalizer.py` | `backend/app/engine/draft_normalizer.py` | Keep\* | `hoist_draft_citations()` added for the classic path; it uses `app.utils.links.split_fences`, like citation coverage and the sign-in annotator. Docstrings still mention upstream's supervisor/presenter. Phase 6: `tag_untagged_drafts()` tags a bare fence holding a placeholder as ```message (```email if it opens with "Subject:"). |
| `backend/scripts/sec_corpus.json` | `backend/scripts/sec_corpus.json` | Keep | Security attack corpus, re-run whenever `input_validator.py` changes. |
| `backend/scripts/sec_test.py` | `backend/scripts/sec_test.py` | Keep\* | Puts `backend/` on `sys.path`: the project isn't installed as a package here, so `import app` failed from `scripts/`. |
| `backend/tests/__init__.py` | `backend/tests/__init__.py` | Keep | — |
| `backend/tests/conftest.py` | `backend/tests/conftest.py` | Keep\* | Sets `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`, so the security tests stop making a Hugging Face request on every validator call. Pre-deploy: `PROMPT_INJECTION_ML_ENABLED=false`, so results don't depend on a cached model. |
| `backend/tests/test_vectordb_client.py` | `backend/tests/test_vectordb_client.py` | Keep\* | Fixtures use `instructor-assistant` instead of `pathway` (the index guard refuses `pathway`); the cache-invalidation test switches to an allow-listed staging name. |
| `backend/tests/test_grounding_guard.py` | `backend/tests/test_grounding_guard.py` | Keep\* | Coverage fixtures now include one citation; new cases for fences, caveats, and wholly uncited answers. |
| `backend/tests/test_security_validation.py` | `backend/tests/test_security_validation.py` | Keep\* | Phase 7 adds tests for the instructor terms (whole words only; never excuse a pattern hit). |
| `backend/tests/test_security_integration.py` | `backend/tests/test_security_integration.py` | Keep | — |
| `backend/tests/test_monitoring_middleware.py` | `backend/tests/test_monitoring_middleware.py` | Keep\* | No metrics-collector stub. |
| `backend/tests/test_langfuse_llama_index_handler.py` | `backend/tests/test_langfuse_llama_index_handler.py` | Adapt | Rewritten for the v4 start/end generation lifecycle. |
| `backend/tests/test_draft_context.py` | `backend/tests/test_draft_context.py` | Keep | — |
| `backend/tests/test_draft_normalizer.py` | `backend/tests/test_draft_normalizer.py` | Keep\* | `hoist_draft_citations` cases added. |
| `backend/tests/test_draft_edit_telemetry.py` | `backend/tests/test_draft_edit_telemetry.py` | Keep\* | Its fake `langfuse` module is removed (with v4 it replaced the real SDK for every later test). It patches `update_current_span`. |
| `backend/tests/test_suggestion_service.py` | `backend/tests/test_suggestion_service.py` | Keep\* | Fixture conversation about pay dates instead of tuition. |
| `backend/tests/test_message_variations_i18n.py` | `backend/tests/test_message_variations_i18n.py` | Keep\* | Removed pools dropped from the parametrization. |
| `backend/tests/test_settings_embed_bounds.py` | `backend/tests/test_settings_embed_bounds.py` | Keep | — |
| `backend/tests/test_user_language_pref.py` | `backend/tests/test_user_language_pref.py` | Keep\* | Geo tiebreaker cases removed. |
| `backend/tests/test_language_detection_bias.py` | `backend/tests/test_language_detection_bias.py` | Keep | — |
| `backend/tests/test_retrieval_orchestrator.py` | `backend/tests/test_retrieval_orchestrator.py` | Adapt | Rewritten for the classic path: guards, callback scoping, synthesis failure, draft-fence hoisting. |
| `frontend/.env.example` | `frontend/.env.example` | Keep\* | Instructor settings only; adds `NEXT_PUBLIC_HELP_URL` and the Sentry build variables; drops the missionary site URL. |
| `frontend/.eslintrc.json` | `frontend/.eslintrc.json` | Keep | — |
| `frontend/.gitignore` | `frontend/.gitignore` | Keep | — |
| `frontend/Dockerfile` | `frontend/Dockerfile` | Keep\* | Release stage holds only `out/` (built from the `.dockerignore` allow-list); serves on `$PORT`; all `NEXT_PUBLIC_*` as build args. |
| `frontend/README.md` | `frontend/README.md` | Adapt | Rewritten for the Instructor Assistant (run, settings, API use, deploy). The false "headers set in next.config.json" claim removed. |
| `frontend/app/components/chat-section.tsx` | `frontend/app/components/chat-section.tsx` | Adapt | Renders the top bar (New chat: clears the chat and starts a new session). Welcome: greeting and starter cards in the middle; the question box stays at the bottom on every screen. Headers are built per request (a new session ID takes effect at once). Privacy line under the box; the note on where answers come from at the bottom. Also: No ACM state, `?acm=`, `role`, dictation, correction, or upload data; starter cards on the empty chat; the "PRIVACY:" notice where "IMPORTANT:" was, always shown; blank input sends nothing; the error banner clears on a new send; no CSS smooth scroll. |
| `frontend/app/components/general-feedback-drawer.tsx` | `frontend/app/components/general-feedback-drawer.tsx` | Keep\* | Upstream's drawer in gold: the send button BYU gold with near-black text; links and focus deep gold `#7A5600`. |
| `frontend/app/components/greeting.tsx` | `frontend/app/components/greeting.tsx` | Adapt | Rewritten: "<time of day>. What can I help with?" in Mulish, and a subtitle. Upstream's random phrase pool, special days, and localStorage are gone. |
| `frontend/app/components/header.tsx` | `frontend/app/components/header.tsx` | Adapt | Rewritten: a BYU-gold bar (light and dark mode) with the BYU-Pathway logo and "Instructor Assistant" on the left, New chat (in a chat) and the gear on the right, all near-black on gold. Props from ChatSection. Title and labels translated. |
| `frontend/app/components/loading-spinner.tsx` | `frontend/app/components/loading-spinner.tsx` | Adapt | The spinner and "Loading..." are replaced by the name "INSTRUCTOR ASSISTANT" with a blue band sweeping through it to the right and back, looping until the app is ready (`.loader-word` in `globals.css`; plain blue with reduced motion). `AppLoader` holds 1 s instead of 800 ms, the length of the sweep. |
| `frontend/app/components/settings-menu.tsx` | `frontend/app/components/settings-menu.tsx` | Keep\* | Upstream's menu: the gear near-black on the gold bar; selected items and hovers in gold tints; the Help item only when `NEXT_PUBLIC_HELP_URL` is set. |
| `frontend/app/components/theme-provider.tsx` | `frontend/app/components/theme-provider.tsx` | Keep | — |
| `frontend/app/components/ui/button.tsx` | `frontend/app/components/ui/button.tsx` | Keep | — |
| `frontend/app/components/ui/chat/chat-input.tsx` | `frontend/app/components/ui/chat/chat-input.tsx` | Adapt | Without uploads, dictation, the role pill, LlamaCloud. A white box with a soft border (gold when focused), a gold send button with a near-black arrow, a dark stop button; blank-Enter guard; `aria-label`. |
| `frontend/app/components/ui/chat/chat-message/UserFeedbackComponent.module.css` | `frontend/app/components/ui/chat/chat-message/UserFeedbackComponent.module.css` | Keep | — |
| `frontend/app/components/ui/chat/chat-message/UserFeedbackComponent.tsx` | `frontend/app/components/ui/chat/chat-message/UserFeedbackComponent.tsx` | Keep\* | Upstream's thumbs as small gray icon buttons (gold when pressed); the comment box's submit in gold; `aria-pressed` and a textarea label added. |
| `frontend/app/components/ui/chat/chat-message/chat-avatar.tsx` | `frontend/app/components/ui/chat/chat-message/chat-avatar.tsx` | Keep | — |
| `frontend/app/components/ui/chat/chat-message/chat-events.tsx` | `frontend/app/components/ui/chat/chat-message/chat-events.tsx` | Keep | — |
| `frontend/app/components/ui/chat/chat-message/chat-sources.tsx` | `frontend/app/components/ui/chat/chat-message/chat-sources.tsx` | Adapt | Upstream's popover and drawer. Citations are gold numbered badges (groups of more than 3 collapse to "+N"); the cited guides show as chips under the answer (one per document; they open the drawer); the drawer lists only cited passages, numbered like their badges; local document/globe icons instead of Google favicons; "Instructor guide (PDF)" / "External page · host"; Escape closes. Exports `ACTION_BUTTON`. Badge and "+N" labels translated; the unused title-pill label helpers removed. |
| `frontend/app/components/ui/chat/chat-message/chat-suggestedQuestions.tsx` | `frontend/app/components/ui/chat/chat-message/chat-suggestedQuestions.tsx` | Adapt | Follow-ups as outlined pills (gold on hover) in place of the italic arrow list; real `<button>`s (upstream's `<a>` had no `href`).  `frontend/app/components/ui/chat/chat-message/copy-utils.ts` | `frontend/app/components/ui/chat/chat-message/copy-utils.ts` | Keep\* | Comment wording only. |
| `frontend/app/components/ui/chat/chat-message/index.tsx` | `frontend/app/components/ui/chat/chat-message/index.tsx` | Adapt | Only the API.md annotations (calendar, tuition, image, file, tool, correction branches removed); `date_spans` passed to Markdown; sources processed once. Under the answer: the source chips, then small copy, thumbs, and regenerate icons, then the follow-ups. User bubble and edit box in the palette. |
| `frontend/app/components/ui/chat/chat-message/markdown.module.css` | `frontend/app/components/ui/chat/chat-message/markdown.module.css` | Keep\* | Blockquote in gold. |
| `frontend/app/components/ui/chat/chat-message/markdown.tsx` | `frontend/app/components/ui/chat/chat-message/markdown.tsx` | Adapt | Calendar ("Block/Term N") and program-catalog heading promotion removed. Answer text 16px in the palette's body color; dates as the pale-gold highlight; a lock icon on sign-in links, and `rehypeSignInNotes` (`sign-in-links.ts`) marks the backend's note so it shows small and gray. |
| `frontend/app/components/ui/chat/chat-message/thumb_request.ts` | `frontend/app/components/ui/chat/chat-message/thumb_request.ts` | Keep | — |
| `frontend/app/components/ui/chat/chat-messages.tsx` | `frontend/app/components/ui/chat/chat-messages.tsx` | Keep\* | Starter-question fetch and (never-shown) rendering removed; they live on the empty chat now (`use-starter-questions.ts`, `starter-questions.tsx`). |
| `frontend/app/components/ui/chat/chat-pending-indicator.tsx` | `frontend/app/components/ui/chat/chat-pending-indicator.tsx` | Keep | — |
| `frontend/app/components/ui/chat/chat.interface.ts` | `frontend/app/components/ui/chat/chat.interface.ts` | Keep | — |
| `frontend/app/components/ui/chat/hooks/use-config.ts` | `frontend/app/components/ui/chat/hooks/use-config.ts` | Keep | — |
| `frontend/app/components/ui/chat/hooks/use-copy-to-clipboard.tsx` | `frontend/app/components/ui/chat/hooks/use-copy-to-clipboard.tsx` | Keep | — |
| `frontend/app/components/ui/chat/hooks/use-throttled-value.ts` | `frontend/app/components/ui/chat/hooks/use-throttled-value.ts` | Keep | — |
| `frontend/app/components/ui/chat/index.ts` | `frontend/app/components/ui/chat/index.ts` | Adapt | Annotation types cut to `events`, `date_spans`, `user_language`, `sources`, `suggested_questions`. `getSourceAnnotationData` is pure and cached per annotation (upstream changed the annotation in place and sorted by score). |
| `frontend/app/components/ui/chat/utils/localization.ts` | `frontend/app/components/ui/chat/utils/localization.ts` | Keep | — |
| `frontend/app/components/ui/chat/widgets/DraftComposer.tsx` | `frontend/app/components/ui/chat/widgets/DraftComposer.tsx` | Keep\* | Upstream's composer; amber placeholder chips are sky blue. Toolbar labels translated (chrome strings); the blue `sky-*` accents are gold. |
| `frontend/app/components/ui/hover-card.tsx` | `frontend/app/components/ui/hover-card.tsx` | Keep | — |
| `frontend/app/components/ui/lib/utils.ts` | `frontend/app/components/ui/lib/utils.ts` | Keep | — |
| `frontend/app/components/ui/toast.tsx` | `frontend/app/components/ui/toast.tsx` | Keep | — |
| `frontend/app/components/ui/tooltip.tsx` | `frontend/app/components/ui/tooltip.tsx` | Keep | — |
| `frontend/app/global-error.tsx` | `frontend/app/global-error.tsx` | Keep\* | Upstream's page with a white (dark: near-black) top bar, a gold button with near-black text, the logo lightened in dark mode; instructor wording. |
| `frontend/app/globals.css` | `frontend/app/globals.css` | Keep\* | Upstream's stylesheet with the gold palette (`--ia-*`, theme-aware), deep-gold / gold focus ring, gold selection, `--highlight-*` for `mark` and dates; the unused link and date-chip colors removed; Mulish in place of Inter; the opening screen's gold sweep (`.loader-word`); no automatic hyphenation. |
| `frontend/app/layout.tsx` | `frontend/app/layout.tsx` | Keep\* | Instructor Assistant metadata; console easter egg removed. Mulish (pinned `@fontsource-variable/mulish` through `next/font/local`) in place of Inter. |
| `frontend/app/lib/chrome-strings.ts` | `frontend/app/lib/chrome-strings.ts` | Adapt | Every interface string in English, Spanish, and Portuguese (upstream's reviewed es/pt wording where it's shared, "Missionary" → "Instructor"); FERPA notice, source-type labels, New chat, welcome heading, and the strings that were hard-coded in components. |
| `frontend/app/lib/draft-registry.ts` | `frontend/app/lib/draft-registry.ts` | Keep | — |
| `frontend/app/lib/i18n.ts` | `frontend/app/lib/i18n.ts` | Adapt | Interface languages trimmed to en/es/pt (an older stored pick reads as auto). |
| `frontend/app/markdown.css` | `frontend/app/markdown.css` | Keep\* | Upstream's styles: links deep gold `#7A5600` (dark: gold) with a gold underline; the citation-chip rules replaced by a reset for the gold badges; `mark` uses `--highlight-bg`; `.signin-note`. |
| `frontend/app/not-found.tsx` | `frontend/app/not-found.tsx` | Keep | — |
| `frontend/app/page.tsx` | `frontend/app/page.tsx` | Adapt | Only `ChatSection` (which now renders the top bar). |
| `frontend/app/utils/session.ts` | `frontend/app/utils/session.ts` | Keep\* | Storage keys renamed `pathway-instructor-assistant-*`; comment wording. |
| `frontend/next.config.json` | `frontend/next.config.json` | Keep\* | `outputFileTracingIncludes` (template server leftovers) removed. |
| `frontend/next.config.mjs` | `frontend/next.config.mjs` | Keep\* | `withLlamaIndex` wrapper and its config migration removed; Sentry org/project from `SENTRY_ORG`/`SENTRY_PROJECT`. |
| `frontend/package-lock.json` | `frontend/package-lock.json` | Keep\* | Regenerated after the dependency changes in `package.json`. |
| `frontend/package.json` | `frontend/package.json` | Keep\* | Renamed `instructor-assistant`; `predev` banner and `generate` scripts removed; 22 unused dependencies dropped (code sandbox, search, LlamaIndex, PDF viewer, …). |
| `frontend/postcss.config.js` | `frontend/postcss.config.js` | Keep | — |
| `frontend/prettier.config.js` | `frontend/prettier.config.js` | Keep | — |
| `frontend/public/BYU-pathway-icon-logo.png` | `frontend/public/BYU-pathway-icon-logo.png` | Keep | — |
| `frontend/public/android-chrome-192x192.png` | `frontend/public/android-chrome-192x192.png` | Keep | — |
| `frontend/public/android-chrome-512x512.png` | `frontend/public/android-chrome-512x512.png` | Keep | — |
| `frontend/public/android-chrome-maskable-192x192.png` | `frontend/public/android-chrome-maskable-192x192.png` | Keep | — |
| `frontend/public/android-chrome-maskable-512x512.png` | `frontend/public/android-chrome-maskable-512x512.png` | Keep | — |
| `frontend/public/apple-touch-icon.png` | `frontend/public/apple-touch-icon.png` | Keep | — |
| `frontend/public/byu-pathway-og-image.jpg` | `frontend/public/byu-pathway-og-image.jpg` | Keep | — |
| `frontend/public/favicon.ico` | `frontend/public/favicon.ico` | Keep | — |
| `frontend/public/gmail.png` | `frontend/public/gmail.png` | Keep | — |
| `frontend/public/ms-outlook.svg` | `frontend/public/ms-outlook.svg` | Keep | — |
| `frontend/public/pathway-horizontal-logo.png` | `frontend/public/pathway-horizontal-logo.png` | Keep | — |
| `frontend/public/serve.json` | `frontend/public/serve.json` | Keep\* | The `fonts/**` cache rule removed (no fonts in `public/` any more). |
| `frontend/public/site.webmanifest` | `frontend/public/site.webmanifest` | Keep\* | Instructor Assistant name and description. |
| `frontend/sentry.client.config.ts` | `frontend/sentry.client.config.ts` | Keep | — |
| `frontend/tailwind.config.ts` | `frontend/tailwind.config.ts` | Keep\* | `sans` is Mulish; the `ia-*` palette colors. |
| `frontend/tsconfig.json` | `frontend/tsconfig.json` | Keep | — |
| `frontend/webpack.config.mjs` | `frontend/webpack.config.mjs` | Keep | — |

New in this repo, with no upstream source: `backend/app/engine/audience_guard.py`,
`backend/app/engine/prompts.py`, `backend/tests/test_audience_guard.py`, `backend/tests/test_chat_api.py`, `backend/tests/test_rerank.py`,
`backend/API.md`, `backend/scripts/api_contract.py`, `backend/scripts/api_check.py`, `backend/tests/test_api_contract.py`, `backend/app/engine/login_links.py`, `backend/app/utils/links.py`, `backend/tests/test_links.py`, `backend/scripts/ask.py`, `backend/tests/test_login_links.py`, `backend/tests/test_prompts_lock.py`, `backend/scripts/retrieve.py`, `backend/scripts/evalset.py`, `backend/scripts/eval_retrieval.py`, `backend/tests/eval/questions.yaml`, `backend/tests/test_evalset.py`, `backend/.env.example` (rewritten from §11), `backend/README.md` (rewritten),
Phase 5: `backend/app/api/tracing.py`, `backend/app/redaction.py`, `backend/scripts/trace_check.py`, `backend/tests/test_tracing.py`.
Phase 6: `backend/scripts/eval_answers.py`, `backend/tests/test_eval_answers.py`.
Phase 7: `backend/.dockerignore`, `DEPLOY.md` (moved to the repo root in Phase 9 prep, now covering both services).
Frontend (Phase 8): `frontend/.dockerignore`, `frontend/app/lib/use-chrome-strings.ts` (2026-10-20, the shared interface-language hook), `frontend/app/components/starter-questions.tsx`, `frontend/app/components/ui/chat/hooks/use-starter-questions.ts`, `frontend/scripts/e2e_check.mjs`, `frontend/app/components/ui/chat/chat-message/sign-in-links.ts` (the lock icon and sign-in note styling). `backend/tests/test_cors_origins.py`.
`scripts/upstream_diff.sh`, `LICENSE`, this file.

Removed from the upstream frontend (Phase 8): the calendar, tuition, weather, and
LlamaCloud widgets; dictation; uploads and file previews; the correction UI; the console
and dev banners; the template `docs/`; the tuition fonts; unused images, icons,
and UI components (`drawer`, `select`, `input`). Gold design (2026-10-20): `disclaimer-message.tsx` (the welcome screen has no disclaimer card; the note on where answers come from is at the bottom).

## Intentional matches for `grep -rniE 'tuition|calendar|agenda|ACM' backend/app`

Phase 0's done-when allows only these:

| File | Why it stays |
| --- | --- |
| `backend/app/security/input_validator.py` | A comment recording that upstream's `CALENDAR_TERMS` were removed (pre-deploy fixes, 2026-10-20). |
| `backend/app/utils/localization.py` | Language-detection word lists ("calendario", "calendar\|tuition" in the English-signal regex). Vocabulary for detecting a language, not features. |
| `backend/app/engine/audience_guard.py` | Docstring: says agenda scope does not take part in the filter. |
| `backend/app/engine/prompts.py` | Docstring: says the tuition facts were not carried over. |
