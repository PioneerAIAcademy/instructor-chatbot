# Instructor Assistant API

The contract between the backend and any client (the Phase 8 frontend, `scripts/ask.py`,
`curl`). It describes what the code sends today. `scripts/api_contract.py` encodes the stream
part as code: `tests/test_api_contract.py` checks it offline, and `scripts/api_check.py`
checks it against a running server. **If you change the stream, change all three.**

Base URL: the backend service, for example `http://localhost:8000`. Interactive docs:
`/api/docs` (it lists only the routes below).

## Common to every request

| Header | When | Meaning |
| --- | --- | --- |
| `X-API-Key` | every `POST` | One of `API_KEYS`. Skipped only when `ENVIRONMENT=dev` and `API_KEYS` is empty; anywhere else an empty `API_KEYS` rejects every request (503). The key ships in the frontend bundle, so it slows abuse down but doesn't control access. |
| `X-Session-ID` | optional | Groups a conversation's traces in Langfuse. The frontend rotates it after 30 minutes idle. Session IDs starting `eval-` mark eval traffic (Phase 5). |
| `X-Device-ID` | optional | Langfuse user ID (a browser fingerprint). |
| `X-Timezone` | optional | IANA name, for example `America/Denver`. Sets "today's date" in the prompt. Default `UTC`. |
| `Content-Length` | every `POST` | Required (411 without it). |

Limits and errors that apply to every `POST`:

| Status | Body | When |
| --- | --- | --- |
| 400 | `{"detail": "Invalid Content-Length header."}` | `Content-Length` isn't a number. |
| 401 | `{"detail": "Unauthorized."}` | Missing or wrong `X-API-Key`. |
| 411 | `{"detail": "Length Required."}` | No `Content-Length` (chunked upload). |
| 413 | `{"detail": "Request body too large. Maximum size is 512KB."}` | Body over 512 KB (10 MB for `/api/v1/chat/feedback/*`). |
| 422 | `{"detail": [ … ]}` | The body fails validation (FastAPI's standard error list). |
| 429 | `{"error": "Rate limit exceeded: 10 per 1 minute"}` | Per client IP; limits are in each route's section. |
| 503 | `{"detail": "Server authentication is not configured."}` | `API_KEYS` is empty outside `ENVIRONMENT=dev`. |

CORS allows only `ALLOWED_ORIGINS` (methods `GET`, `POST`, `OPTIONS`; headers `Content-Type`,
`X-API-Key`, `X-Session-ID`, `X-Device-ID`, `X-Timezone`). `CORS_ALLOW_ALL=true` is for local
development only.

## `POST /api/v1/chat`

Ask a question. Rate limit 10/minute per IP. The response is a stream.

### Request

```json
{
  "messages": [
    {"role": "user", "content": "When do I get paid?"},
    {"role": "assistant", "content": "You're paid on the 8th and 23rd [^1]."},
    {"role": "user", "content": "And from Brazil?"}
  ],
  "data": {
    "user_language_pref": "pt",
    "edited_draft": {"body": "Hi [Student Name], …", "subject": "Welcome", "draft_type": "message"}
  }
}
```

- `messages` (required): 1 to 50 messages. Each `role` is `user` or `assistant`, and the last
  message must be `user`; anything else is a 422. The last message may be at most 10 KB. Earlier
  messages are chat history; the client keeps it, and the server stores nothing.
  `annotations` on a message is accepted and ignored.
- The last message goes through the input security screen (2,000 characters at most; prompt
  injection patterns). A blocked message still gets a `200` stream, with a canned reply (see
  "Blocked input").
- `data` (optional):
  - `user_language_pref`: a language code, or `"auto"`. It's used only when the question's own
    language can't be detected confidently (a very short question). The answer follows the
    question's language.
  - `edited_draft`: the user's edits to a drafted message, from the draft composer: `body`,
    optional `subject`, `draft_type` `"email"` or `"message"`. The edits are screened too. If
    they're rejected, the model is told it can't see them.
  - `role`: **ignored.** The audience is fixed to instructors on the server. A value other than
    `instructor` is logged.
  - Anything else is ignored.

### Response stream

`200`, `Content-Type: text/event-stream`. The body is the Vercel AI SDK data-stream format: one
item per line, `<prefix>:<JSON>`, each followed by blank padding lines (they force the proxy
to flush; skip blank lines).

| Prefix | Payload | Meaning |
| --- | --- | --- |
| `0:` | a JSON string | A piece of the answer text. Concatenate them in order. The stream opens with `0:""`. |
| `8:` | a JSON list of annotation objects | Structured data (below). |

No other prefixes are sent. A failure is never sent as an error line; see "Failed answer".

Every annotation is `{"type": …, "data": …, "trace_id": …}`. `trace_id` is the Langfuse trace
ID: pass it to `/thumbs_request`. It's `null` when tracing is off. They arrive in this order:

1. **`events`** (zero or more, interleaved with the text): a status tick for the "thinking"
   indicator, in the language of the question.
   ```json
   {"type": "events", "data": {"title": "Searching knowledge base..."}, "trace_id": "…"}
   ```
2. **`date_spans`** (only when the answer contains dates): phrases the frontend highlights.
   ```json
   {"type": "date_spans", "data": {"phrases": ["October 21, 2026"], "language": "en"}, "trace_id": "…"}
   ```
3. **`user_language`**: the language the UI should switch to.
   ```json
   {"type": "user_language", "data": {"language": "pt"}, "trace_id": "…"}
   ```
4. **`sources`**: the documents behind the answer. Each `[^N]` in the text maps to the node whose
   `citation_node_id` is `"N"`.
   ```json
   {"type": "sources", "data": {"nodes": [
     {
       "id": "pay-dates-for-worldwide-online-instructors-ia#0002",
       "citation_node_id": "1",
       "url": "https://missionaries.prod.byu-pathway.psdops.com/pay-dates-for-worldwide-online-instructors-ia",
       "score": 0.81,
       "text": "…the merged text of this document's retrieved chunks…",
       "metadata": {
         "url": "…same as url…", "title": "Pay Dates for Worldwide Online Instructors",
         "slug": "pay-dates-for-worldwide-online-instructors-ia",
         "source": "instructor-assistant", "role": "instructor", "sequence": 2,
         "header_1": "…", "rerank_relevance": 0.87, "node_id": "…"
       }
     }
   ]}, "trace_id": "…"}
   ```
   - `url` is the citation link. For an instructor guide (`metadata.source` =
     `instructor-assistant`) it's the public PDF. For a linked page
     (`instructor-assistant-linked`) it's the page itself. Label linked pages as external,
     for example "External page · <host>".
   - `metadata.role` is always `instructor`; a server-side guard drops anything else.
   - Metadata keys beyond those in the example may appear (`header_2`…`header_6`,
     `content_hash`, `linked_from`, …). Ignore unknown keys.
5. **`suggested_questions`** (when generation succeeded): follow-up questions, in the
   question's language.
   ```json
   {"type": "suggested_questions", "data": ["When is the next pay day?"], "trace_id": "…"}
   ```

### What's in the answer text

- Markdown. Citations are inline `[^N]` markers right after the claim.
- Links to pages that need a BYU-Pathway or BYU-Idaho sign-in (SharePoint and OneDrive, the
  course directory, Companion, the portal) are followed by a note in the answer's language,
  such as `(sign-in required)` or `(requer login)`.
- Every URL in the text appears in a source's `url` or `text`; invented links are removed.
- A drafted announcement, email or message is in a fenced block tagged `message` or `email`.
  The block holds plain text only, with no `[^N]` and no sign-in notes; its citations sit on
  the line after the fence. This is what mounts the frontend's draft composer.

### Blocked input

The stream carries a short refusal as text, then `user_language` and an empty
`sources.data.nodes`, and no `suggested_questions`.

### Failed answer

If the model or retrieval fails, or the stream stalls (180 s before the first text, 45 s
between pieces), the stream carries a short apology as text, in the question's language
("Sorry — I hit a service hiccup. Please try asking again."), and no `sources` or
`suggested_questions`. The status is still `200`, because the stream had already started.
Clients should treat "no `sources` annotation" as a failed answer.

Errors before the stream starts are plain JSON: `500 {"detail": "An error occurred. Please try
again."}`. In `ENVIRONMENT=dev` the detail includes the exception.

## `POST /api/v1/chat/thumbs_request`

Thumbs up or down on an answer. Rate limit 30/minute. It's recorded as the Langfuse score
`user_feedback` on the trace.

```json
{"trace_id": "…from the stream…", "value": "bad", "comment": "The pay dates are wrong."}
```

- `value`: `"good"`, `"bad"`, or `""` to clear (case-insensitive).
- `comment` is kept only with `"bad"`; it's cleared otherwise.

Response `200`: `{"feedback": "Bad"}` (or `"Good"`, or `""`).

## `POST /api/v1/chat/feedback/general`

General feedback, not tied to an answer. Rate limit 5/minute. `multipart/form-data`:

| Field | Required | Meaning |
| --- | --- | --- |
| `feedback` | yes | The text. Empty gives a 422. |
| `screenshot` | no | An image, up to 10 MB. Stored in Cloudinary (`instructor-assistant/feedback`). Without Cloudinary configured: `500 {"detail": "Screenshot uploads are not configured"}`. Not an image: 400. |

Response `200`: `{"status": "success", "message": "Thank you for your feedback!"}`.

## `POST /api/v1/chat/draft/edit`

Rewrite a selected part of a drafted message, from the draft composer. Rate limit 20/minute.

```json
{
  "draft_type": "message",
  "instruction": "Make it warmer",
  "selected_text": "Hi [Student Name].",
  "full_content": "Hi [Student Name]. Welcome to [Course].",
  "subject": null
}
```

- `draft_type`: `"email"` or `"message"`.
- `instruction`: 1 byte to 2 KB, required.
- `selected_text`: 1 byte to 12 KB, required.
- `full_content`: up to 64 KB.
- `subject`: optional.

The instruction goes through the security screen.

Response `200`:

```json
{"edited_text": "Hi [Student Name], welcome!", "blocked": false, "message": null, "reason": "ok"}
```

When no edit is made, `edited_text` is `null`, `blocked` is `true`, `message` is text to show
the user, and `reason` is one of:
- `security_validation_failed`: the instruction was blocked;
- `invalid_edit_instruction`: it isn't an edit request;
- `edit_rejected`: the rewrite failed checks, or the model call failed.

## `GET /api/v1/chat/config`

No auth. Starter questions for an empty chat, from `CONVERSATION_STARTERS`: one per line, and a
literal `\n` also separates them.

```json
{"starterQuestions": ["When do I get paid?", "Write a welcome message for my students."]}
```

`{"starterQuestions": null}` when none are configured.

## `GET /api/health` and `GET /api/health/ready`

No auth.

- `/api/health` is liveness: `{"status": "ok"}`.
- `/api/health/ready` is readiness:
  ```json
  {"status": "ok", "index": "instructor-assistant", "guard": "ok"}
  ```
  - `status` is `"degraded"` when Pinecone (a data-plane read) or Langfuse isn't reachable.
  - `guard` is `"error"` when the index guard refuses the configuration. A server can only be
    in that state if the environment changed after boot.
  - Which dependency failed is logged, not returned.
