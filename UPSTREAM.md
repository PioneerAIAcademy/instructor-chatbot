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
| `.githooks/pre-push` | `.githooks/pre-push` | Keep\* | Frontend `tsc`/`lint` removed until Phase 8. |
| `.githooks/README.md` | `.githooks/README.md` | Keep\* | Lists all three hooks; activation via `setup-dev.sh`. |
| `.github/workflows/payload-guard.yml` | `.github/workflows/payload-guard.yml` | Keep | — |
| `.github/workflows/test.yml` | `.github/workflows/test.yml` | Keep\* | Backend job only until Phase 8. Poetry 2.4.1 (the version that wrote `poetry.lock`) instead of 1.8.2. |
| `scripts/setup-dev.sh` | `scripts/setup-dev.sh` | Keep\* | Rule and context references point to CLAUDE.md. |
| `docs/agent-onboarding/journal-skill/SKILL.md` | `docs/agent-onboarding/journal-skill/SKILL.md` | Keep\* | CLAUDE.md is committed here, so it must never hold secrets. |
| `.gitignore` | `.gitignore` | Adapt | Rewritten. `.claude/agents/` stays tracked. |
| `backend/.gitignore` | `backend/.gitignore` | Keep\* | Tuition/calendar data lines dropped; `tests/eval/results/` added. |
| `backend/Dockerfile` | `backend/Dockerfile` | Keep\* | Stale comments (web loader, spacy) removed. |
| `backend/pyproject.toml` | `backend/pyproject.toml` | Adapt | `llama-index` meta-package replaced by the four parts the chat path imports (same locked versions). Dropped: spacy, llama-cloud, arize-phoenix, pandas/pyarrow/boto3/apscheduler, docx2txt, jupyterlab, unused security pins. |
| `backend/poetry.lock` | `backend/poetry.lock` | Adapt | Re-locked with `poetry lock` (Poetry 2.4.1, which keeps existing versions); 270 → 125 packages. Every remaining package kept its upstream-locked version. |
| `backend/main.py` | `backend/main.py` | Adapt | Boot runs `check_index_config()` and refuses a wrong index or host. Only chat, config, health routers. No calendar/tuition/dictation/upload routers, file server, block-date or tuition schedulers, or S3 monitoring scheduler. The dev root redirect goes to `/api/docs` (upstream pointed at `/docs`, a 404). |
| `backend/app/__init__.py` | `backend/app/__init__.py` | Keep | — |
| `backend/app/auth.py` | `backend/app/auth.py` | Keep | — |
| `backend/app/langfuse.py` | `backend/app/langfuse.py` | Keep | — |
| `backend/app/observability.py` | `backend/app/observability.py` | Keep | — |
| `backend/app/http_client.py` | `backend/app/http_client.py` | Keep | — |
| `backend/app/memory_trim.py` | `backend/app/memory_trim.py` | Keep | — |
| `backend/app/settings.py` | `backend/app/settings.py` | Keep\* | OpenAI provider only (llmhub and the other providers dropped). |
| `backend/app/security/__init__.py` | `backend/app/security/__init__.py` | Keep | — |
| `backend/app/security/input_validator.py` | `backend/app/security/input_validator.py` | Keep | Unchanged on purpose. Instructor terms are added later, together with a security-corpus re-run (CLAUDE.md §4 Adapt). |
| `backend/app/middleware/monitoring_middleware.py` | `backend/app/middleware/monitoring_middleware.py` | Keep\* | S3 metrics-collector calls (`app.monitoring`, not ported) removed. Request IDs, 499 on disconnect, and crash logging unchanged. |
| `backend/app/utils/langfuse_llama_index.py` | `backend/app/utils/langfuse_llama_index.py` | Keep | — |
| `backend/app/utils/localization.py` | `backend/app/utils/localization.py` | Keep\* | Agenda-not-found and missionary site-index strings, and the geo country map, removed. |
| `backend/app/utils/date_spans.py` | `backend/app/utils/date_spans.py` | Keep | Feeds the frontend's date highlighting in any answer, so it isn't calendar-only. |
| `backend/app/api/__init__.py` | `backend/app/api/__init__.py` | Keep | — |
| `backend/app/api/routers/__init__.py` | `backend/app/api/routers/__init__.py` | Keep | — |
| `backend/app/api/routers/chat.py` | `backend/app/api/routers/chat.py` | Adapt | Rewritten around the classic path. Language is resolved from the typed message, before the edited-draft block is appended. A screened-out edited draft adds a notice telling the model it can't see the edits. Ignores `data.role` (warns if it isn't `instructor`). Filter is `instructor_filters()`. No geo lookup, agenda scope, widget router, calendar/tuition, supervisor, ACM prefix, or `/request`. Draft edit, thumbs, and general feedback kept. Cloudinary folder `instructor-assistant/feedback`. `role:instructor` tag on draft-edit and feedback traces. |
| `backend/app/api/routers/chat_config.py` | `backend/app/api/routers/chat_config.py` | Keep\* | LlamaCloud route removed. |
| `backend/app/api/routers/events.py` | `backend/app/api/routers/events.py` | Keep | — |
| `backend/app/api/routers/health.py` | `backend/app/api/routers/health.py` | Keep\* | `/health/ready` also returns `index` and `guard`; it skips the Pinecone call when the guard refuses the config. |
| `backend/app/api/routers/message_variations.py` | `backend/app/api/routers/message_variations.py` | Keep\* | Calendar, graduation, pushback, and text-format status pools removed. |
| `backend/app/api/routers/models.py` | `backend/app/api/routers/models.py` | Adapt | File-server URL rewrite and `DATA_DIR` import removed. Client messages may only be `user`/`assistant`, and the last must be `user`. `get_last_message_content` no longer merges `document_file` annotations into the prompt (upstream's `if not filter(...)` check never fired). `get_chat_document_ids` removed. |
| `backend/app/api/routers/vercel_response.py` | `backend/app/api/routers/vercel_response.py` | Adapt | Calendar paths, supervisor emit queue, stream-first correction, and prebuilt annotations removed. Streams text, `events`, `date_spans`, `user_language`, `sources`, `suggested_questions`. Any answer failure (not only a hang) streams the localized hiccup text; upstream sent `str(exc)` as a `3:` error. |
| `backend/app/api/services/draft_edit.py` | `backend/app/api/services/draft_edit.py` | Keep\* | Persona is the Instructor Assistant; the students/learners terminology line dropped. |
| `backend/app/api/services/suggestion.py` | `backend/app/api/services/suggestion.py` | Keep\* | Prompt rewritten for instructors (first person, "students"). |
| `backend/app/engine/__init__.py` | `backend/app/engine/__init__.py` | Adapt | `AudienceGuardPostprocessor` runs first among the postprocessors. Same wiring (top_k 35, sparse 175, 24K memory). Prompts come from `prompts.py`. No temporal status, tuition facts, or program ladder. |
| `backend/app/engine/vectordb.py` | `backend/app/engine/vectordb.py` | Keep\* | `get_vector_store()` calls `check_index_config(index_name, PINECONE_INDEX_HOST)` before building a client, which closes the host-overrides-name path. |
| `backend/app/engine/index.py` | `backend/app/engine/index.py` | Keep | — |
| `backend/app/engine/node_postprocessors.py` | `backend/app/engine/node_postprocessors.py` | Keep | — |
| `backend/app/engine/custom_node_with_score.py` | `backend/app/engine/custom_node_with_score.py` | Keep | — |
| `backend/app/engine/custom_condense_plus_context.py` | `backend/app/engine/custom_condense_plus_context.py` | Keep\* | `audience_marker` replaced by `source_label` (instructor guide vs external page). `clean_retrieved_text` (missionary-corpus rules) dropped. Rerank model, top-k, and 0.21 cutoff moved to module constants (same values) so `scripts/retrieve.py` reranks identically. |
| `backend/app/engine/grounding_guard.py` | `backend/app/engine/grounding_guard.py` | Keep\* | `ensure_citation_coverage` skips fenced blocks (and their fence lines) and wholly uncited answers. More English caveat/refusal openers are exempt. Docstrings still describe upstream's agentic loop. |
| `backend/app/engine/retrieval_orchestrator.py` | `backend/app/engine/retrieval_orchestrator.py` | Adapt | Classic engine, then drain, then `apply_grounding_guards`, then `hoist_draft_citations`. No recency engine or critic. A guard failure ships the unguarded draft. A failed or empty answer stream raises `SynthesisFailedError`. The per-request `EventCallbackHandler` goes on a per-request CallbackManager; upstream appends it to the global `Settings.callback_manager`, which leaks handlers and mixes status events across requests. |
| `backend/app/engine/draft_context.py` | `backend/app/engine/draft_context.py` | Keep\* | `build_dropped_draft_notice()` added. Upstream's `chat.py` comment promised to tell the model, but it only logged. |
| `backend/app/engine/draft_normalizer.py` | `backend/app/engine/draft_normalizer.py` | Keep\* | `hoist_draft_citations()` added for the classic path. Docstrings still mention upstream's supervisor/presenter. |
| `backend/scripts/sec_corpus.json` | `backend/scripts/sec_corpus.json` | Keep | Security attack corpus, re-run whenever `input_validator.py` changes. |
| `backend/scripts/sec_test.py` | `backend/scripts/sec_test.py` | Keep\* | Puts `backend/` on `sys.path`: the project isn't installed as a package here, so `import app` failed from `scripts/`. |
| `backend/tests/__init__.py` | `backend/tests/__init__.py` | Keep | — |
| `backend/tests/conftest.py` | `backend/tests/conftest.py` | Keep | — |
| `backend/tests/test_vectordb_client.py` | `backend/tests/test_vectordb_client.py` | Keep\* | Fixtures use `instructor-assistant` instead of `pathway` (the index guard refuses `pathway`); the cache-invalidation test switches to an allow-listed staging name. |
| `backend/tests/test_grounding_guard.py` | `backend/tests/test_grounding_guard.py` | Keep\* | Coverage fixtures now include one citation; new cases for fences, caveats, and wholly uncited answers. |
| `backend/tests/test_security_validation.py` | `backend/tests/test_security_validation.py` | Keep | — |
| `backend/tests/test_security_integration.py` | `backend/tests/test_security_integration.py` | Keep | — |
| `backend/tests/test_monitoring_middleware.py` | `backend/tests/test_monitoring_middleware.py` | Keep\* | No metrics-collector stub. |
| `backend/tests/test_langfuse_llama_index_handler.py` | `backend/tests/test_langfuse_llama_index_handler.py` | Keep | — |
| `backend/tests/test_draft_context.py` | `backend/tests/test_draft_context.py` | Keep | — |
| `backend/tests/test_draft_normalizer.py` | `backend/tests/test_draft_normalizer.py` | Keep\* | `hoist_draft_citations` cases added. |
| `backend/tests/test_draft_edit_telemetry.py` | `backend/tests/test_draft_edit_telemetry.py` | Keep | — |
| `backend/tests/test_suggestion_service.py` | `backend/tests/test_suggestion_service.py` | Keep\* | Fixture conversation about pay dates instead of tuition. |
| `backend/tests/test_message_variations_i18n.py` | `backend/tests/test_message_variations_i18n.py` | Keep\* | Removed pools dropped from the parametrization. |
| `backend/tests/test_settings_embed_bounds.py` | `backend/tests/test_settings_embed_bounds.py` | Keep | — |
| `backend/tests/test_user_language_pref.py` | `backend/tests/test_user_language_pref.py` | Keep\* | Geo tiebreaker cases removed. |
| `backend/tests/test_language_detection_bias.py` | `backend/tests/test_language_detection_bias.py` | Keep | — |
| `backend/tests/test_retrieval_orchestrator.py` | `backend/tests/test_retrieval_orchestrator.py` | Adapt | Rewritten for the classic path: guards, callback scoping, synthesis failure, draft-fence hoisting. |

New in this repo, with no upstream source: `backend/app/engine/audience_guard.py`,
`backend/app/engine/prompts.py`, `backend/tests/test_audience_guard.py`, `backend/tests/test_chat_api.py`,
`backend/scripts/retrieve.py`, `backend/.env.example` (rewritten from §11), `backend/README.md` (rewritten),
`scripts/upstream_diff.sh`, this file.

## Intentional matches for `grep -rniE 'tuition|calendar|agenda|ACM' backend/app`

Phase 0's done-when allows only these:

| File | Why it stays |
| --- | --- |
| `backend/app/security/input_validator.py` | `CALENDAR_TERMS` and `_allow_calendar_false_positive` are the security screen's allowlist. Words like "calendar" and "deadline" are legitimate in instructor questions. Changing the screen needs a security-corpus re-run (CLAUDE.md §4 Adapt), so it stays byte-identical for now. |
| `backend/app/utils/localization.py` | Language-detection word lists ("calendario", "calendar\|tuition" in the English-signal regex). Vocabulary for detecting a language, not features. |
| `backend/app/engine/audience_guard.py` | Docstring: says agenda scope does not take part in the filter. |
| `backend/app/engine/prompts.py` | Docstring: says the tuition facts were not carried over. |
