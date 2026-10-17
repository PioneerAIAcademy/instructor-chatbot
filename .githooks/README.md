# Versioned git hooks

These hooks are checked into the repo so every contributor runs the same
checks. They are **not** active by default — `core.hooksPath` is a per-clone
setting.

## Activate once per clone

```sh
bash scripts/setup-dev.sh   # sets core.hooksPath = .githooks
```

## Hooks

- **`commit-msg`** — blocks AI / co-author attribution (CLAUDE.md §0 rule 1).
- **`pre-push`** — backend `pytest tests/`, keyless like CI. Frontend
  `tsc --noEmit` + `next lint` join in Phase 8. Catches the same things CI
  catches, just before they leave your machine.
- **`post-commit`** — intentionally empty.

## Bypass

For a single push (rare — only when you know the failure is unrelated):

```sh
git push --no-verify
```

If you find yourself bypassing often, fix the hook or fix the test —
don't normalize bypassing.
