#!/usr/bin/env bash
# setup-dev.sh — one-time per-clone activation of the project's guardrails.
# Idempotent: safe to run repeatedly.
#
#   bash scripts/setup-dev.sh
#
# It (1) points git at the shared hooks, (2) installs the /journal skill if the
# current agent doesn't already have it, and (3) prints the rules in orange.

set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ -t 1 ]; then ORANGE=$'\033[1;38;5;208m'; GREEN=$'\033[1;32m'; DIM=$'\033[2m'; RESET=$'\033[0m'; else ORANGE=''; GREEN=''; DIM=''; RESET=''; fi

echo ""
echo "${ORANGE}🟧  Activating project guardrails…${RESET}"

# 1) Shared git hooks (commit-msg = block AI/co-author attribution; pre-push =
#    CI-parity tests; post-commit = journal reminder).
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "${GREEN}  ✓ git hooks active (core.hooksPath = .githooks)${RESET}"

# 2) Install the /journal skill for the agent if it's missing, so "always
#    journal" is actually possible for a brand-new agent on this machine.
SKILL_SRC="$REPO_ROOT/docs/agent-onboarding/journal-skill/SKILL.md"
SKILL_DST_DIR="$HOME/.claude/skills/journal"
if [ -f "$SKILL_DST_DIR/SKILL.md" ]; then
  echo "${GREEN}  ✓ /journal skill already installed${RESET}"
elif [ -f "$SKILL_SRC" ]; then
  mkdir -p "$SKILL_DST_DIR"
  cp "$SKILL_SRC" "$SKILL_DST_DIR/SKILL.md"
  echo "${GREEN}  ✓ /journal skill installed → $SKILL_DST_DIR/SKILL.md${RESET}"
  echo "${DIM}    (restart your agent CLI if it doesn't see the skill yet)${RESET}"
else
  echo "${ORANGE}  ⚠  journal skill source missing ($SKILL_SRC) — set up /journal manually${RESET}"
fi

echo ""
echo "${ORANGE}╔════════════════════════════════════════════════════════════════════╗${RESET}"
echo "${ORANGE}║  🟧  TWO RULES THAT ARE NEVER OPTIONAL ON THIS REPO                 ║${RESET}"
echo "${ORANGE}║   1. NEVER add Co-Authored-By / \"Generated with …\" / 🤖 to commits. ║${RESET}"
echo "${ORANGE}║      (commit-msg hook HARD-BLOCKS it.)                             ║${RESET}"
echo "${ORANGE}║   2. ALWAYS /journal — update CLAUDE.md every session.             ║${RESET}"
echo "${ORANGE}║   • Agents must NEVER push to main (CLAUDE.md §0 rule 3).           ║${RESET}"
echo "${ORANGE}╚════════════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo "${DIM}  Context for this repo lives in CLAUDE.md (plan, rules, and the §14 journal).${RESET}"
echo ""
