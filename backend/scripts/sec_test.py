"""Scratch security harness — run the attack corpus through the REAL production
input-validation gate (app.security.InputValidator.validate_input_security_async),
no mocks, no rate limit. A case is BLOCKED iff the gate returns a non-empty
blocked_message (length>2000, or risk MEDIUM/CRITICAL and not allowlisted).

Usage: poetry run python scripts/sec_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Scripts run as `poetry run python scripts/<name>.py`; put backend/ on the
# path so `app` imports (the project is not installed as a package).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security.input_validator import InputValidator  # noqa: E402

HERE = os.path.dirname(__file__)


def _family_tags(patterns: list[str]) -> str:
    fams = []
    for p in patterns:
        if p.startswith("system_pattern"):
            fams.append("system")
        elif p.startswith("variable_pattern"):
            fams.append("variable")
        elif p.startswith("suspicious_keyword"):
            fams.append("keyword")
        elif p.startswith("format_pattern"):
            fams.append("format")
        elif p.startswith("social_engineering"):
            fams.append("social")
        elif p.startswith("pytector"):
            fams.append("pytector")
        elif p == "excessive_length":
            fams.append("length")
        elif p == "high_special_char_ratio":
            fams.append("special-char")
        else:
            fams.append(p)
    # dedup preserving order
    seen, out = set(), []
    for f in fams:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return ",".join(out) or "-"


async def main() -> None:
    with open(os.path.join(HERE, "sec_corpus.json"), encoding="utf-8") as fh:
        corpus = json.load(fh)

    print("[warming pytector detector...]", flush=True)
    InputValidator.get_pytector_detector()
    print("[ready — running corpus]", flush=True)

    rows = []
    misses_gap = []   # should block, gate ALLOWED  -> security gap
    misses_fp = []    # should pass, gate BLOCKED   -> false positive
    n_ok = 0

    for i, case in enumerate(corpus, 1):
        text = case["text"]
        if text == "__OVER_LIMIT_AAAA__":
            text = "A" * 2500
        is_susp, blocked_msg, details = await InputValidator.validate_input_security_async(text)
        print(f"  [{i:>2}/{len(corpus)}] {('BLOCKED' if blocked_msg else 'ALLOWED'):<8} {case['name']}", flush=True)
        blocked = bool(blocked_msg)
        verdict = "BLOCKED" if blocked else "ALLOWED"
        expected_block = case["expected"] == "block"
        ok = blocked == expected_block
        if ok:
            n_ok += 1
        elif expected_block:
            misses_gap.append(case["name"])
        else:
            misses_fp.append(case["name"])

        rows.append({
            "i": i,
            "name": case["name"],
            "exp": "BLOCK" if expected_block else "PASS",
            "verdict": verdict,
            "ok": ok,
            "len": len(text),
            "risk": details.get("risk_level", "LOW"),
            "score": details.get("risk_score", "-"),
            "fams": _family_tags(details.get("detected_patterns", [])),
            "reason": details.get("reason", ""),
        })

    # ---- print table ----
    print(f"\n{'#':>2}  {'EXP':<5} {'VERDICT':<8} {'OK':<3} {'LEN':>5} {'RISK':<8} {'SC':>3}  NAME / matched-families")
    print("-" * 110)
    for r in rows:
        mark = "✓" if r["ok"] else "✗ <<<"
        print(f"{r['i']:>2}  {r['exp']:<5} {r['verdict']:<8} {mark:<5} {r['len']:>5} {r['risk']:<8} "
              f"{str(r['score']):>3}  {r['name']}")
        print(f"{'':>34}[{r['fams']}]" + (f"  reason={r['reason']}" if r['reason'] else ""))

    total = len(rows)
    print("\n" + "=" * 60)
    print(f"RESULT: {n_ok}/{total} matched expectation")
    print(f"  attacks correctly BLOCKED: "
          f"{sum(1 for r in rows if r['exp']=='BLOCK' and r['verdict']=='BLOCKED')}"
          f"/{sum(1 for r in rows if r['exp']=='BLOCK')}")
    print(f"  legit correctly ALLOWED:   "
          f"{sum(1 for r in rows if r['exp']=='PASS' and r['verdict']=='ALLOWED')}"
          f"/{sum(1 for r in rows if r['exp']=='PASS')}")
    if misses_gap:
        print(f"\n  ⚠️  SECURITY GAP (should block, gate ALLOWED) -> {misses_gap}")
        print("     (these rely on downstream LLM/grounding defenses — verify via full chatbot)")
    if misses_fp:
        print(f"\n  ⚠️  FALSE POSITIVE (should pass, gate BLOCKED) -> {misses_fp}")
    if not misses_gap and not misses_fp:
        print("\n  ✅ gate matched every expectation")


if __name__ == "__main__":
    asyncio.run(main())
