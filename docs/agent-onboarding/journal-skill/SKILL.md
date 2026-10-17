---
name: journal
description: Use at the start, middle, and end of EVERY session to read and update the project journal (CLAUDE.md) — the single source of truth for status, architecture, lessons, and what has failed.
---

# Project Journal & Context

## On Session Start (ALWAYS do this first)
1. Read `CLAUDE.md` from the project root — the single source of truth for
   project context, history, architecture, lessons learned, and deployment status.
2. Summarize the current project status to the user in 2-3 sentences.

## During Work
- Reference CLAUDE.md when making decisions.
- It contains hard-won lessons (things that failed, golden parameters that must
  not change). Check "Lessons Learned" and "Things That FAILED" before trying
  approaches.

## Before Finishing Work (ALWAYS do this)
1. Update `CLAUDE.md` with:
   - What was done this session (under a dated session entry).
   - New findings, breakthroughs, or bugs found.
   - Updated "Current Status" with the new date.
   - New technical details, gotchas, or architecture changes.
   - New lessons learned / things that failed.
   - Updated "Next Steps".
2. Keep it concise but thorough — long is fine if every line is critical for the
   next session.
3. Remove outdated/superseded info rather than accumulating stale entries.

## Rules
- NEVER overwrite the user's personal edits in CLAUDE.md.
- CLAUDE.md is BOTH a technical reference for the agent AND a readable journal
  for the user.
- In instructor-chatbot, CLAUDE.md is committed (the repo is public). Never
  write a secret, key, or credential-bearing hostname into it (§0 rule 4). The
  journal is §14; add newest entries first.
- Update the "Last updated" date at the top when modifying.
- No arbitrary line limit — include everything CRITICAL and USEFUL, trim the rest.
