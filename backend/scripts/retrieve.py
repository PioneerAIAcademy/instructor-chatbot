"""Raw and reranked retrieval for one question, through the production path.

    poetry run python scripts/retrieve.py "When do instructors get paid?"
    poetry run python scripts/retrieve.py "..." --expect pay-dates-for-worldwide-online-instructors-ia

LIVE AND BILLABLE: one OpenAI query embedding, one Pinecone query, and (with
2+ unique texts) one Voyage rerank. Uses the same index guard, filter,
retriever (top 35), audience postprocessor, and rerank function
(`rerank_nodes`) as /api/v1/chat, so a skipped or failed rerank is reported
the way production handles it. No LLM answer is generated. Read-only against
Pinecone.

Prints the index, then every raw and reranked node's slug, source, role, and
score. With --expect, reports the expected slug's rank after rerank and exits
1 if it isn't in the top 5 (or the guard dropped anything). Never prints keys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# The project is not installed as a package; put backend/ on the path, and
# scripts/ for the shared evalset module.
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")


def _row(rank: int, score: float | None, metadata: dict) -> str:
    title = (metadata.get("title") or "")[:48]
    score_txt = f"{score:.3f}" if isinstance(score, (int, float)) else "  -  "
    return (
        f"{rank:>3}  {score_txt}  {metadata.get('slug', '?'):<58}  "
        f"{metadata.get('source', '?'):<28}  {metadata.get('role', '?'):<10}  {title}"
    )


def prepare() -> str:
    """One-time setup: the index guard and the LLM/embedding settings.

    Returns the index name. Call once before run_retrieval(); the eval calls
    it once for all its questions instead of once per question.
    """
    from app.engine.audience_guard import check_index_config
    from app.settings import init_settings

    index_name = check_index_config()
    init_settings()
    return index_name


def run_retrieval(question: str, index_name: str | None = None) -> dict:
    """Return the retrieval for one question through the production path.

    Keys: index, raw and reranked (lists of (score, metadata) in rank order),
    dropped (audience-guard drops), rerank_attempted, rerank_ok, rerank_error,
    min_score. Reranking goes through the engine's own `rerank_nodes`, so the
    rules can't drift from production. Pass `index_name` from prepare() to
    skip the setup; without it, prepare() runs first. Reused by the eval.
    """
    from llama_index.core import QueryBundle

    from app.engine import get_chat_engine
    from app.engine.audience_guard import instructor_filters
    from app.engine.custom_condense_plus_context import RERANK_MIN_SCORE, rerank_nodes

    if index_name is None:
        index_name = prepare()

    # A fresh engine per question, as production builds one per request: it
    # owns this question's audience guard (and its drop count). The vector
    # store under it is cached, so this is cheap.
    engine = get_chat_engine(filters=instructor_filters())
    raw_nodes = engine._retriever.retrieve(question)
    raw = [(n.score, dict(n.node.metadata)) for n in raw_nodes]

    nodes = raw_nodes
    for postprocessor in engine._node_postprocessors:
        nodes = postprocessor.postprocess_nodes(nodes, query_bundle=QueryBundle(question))

    outcome = rerank_nodes(nodes, question)
    reranked = [(n.node.metadata.get("rerank_relevance"), dict(n.node.metadata)) for n in outcome.nodes]

    return {
        "index": index_name,
        "raw": raw,
        "reranked": reranked,
        "dropped": engine.audience_guard.dropped,
        "rerank_attempted": outcome.attempted,
        "rerank_ok": outcome.success,
        "rerank_error": repr(outcome.error) if outcome.error else None,
        "min_score": RERANK_MIN_SCORE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("question")
    parser.add_argument("--expect", help="slug or linked-page URL that should rank in the top 5 after rerank")
    args = parser.parse_args()

    result = run_retrieval(args.question)
    header = f"{'#':>3}  {'score':<5}  {'slug':<58}  {'source':<28}  {'role':<10}  title"

    print(f"index: {result['index']}")
    print(f"question: {args.question}\n")
    print(f"RAW (filtered, top {len(result['raw'])})")
    print(header)
    for i, (score, meta) in enumerate(result["raw"], 1):
        print(_row(i, score, meta))

    if not result["rerank_attempted"]:
        print(f"\nRERANKED: skipped ({len(result['reranked'])} unique text(s); no rerank, no cutoff)")
    elif not result["rerank_ok"]:
        print(
            f"\nRERANKED: Voyage failed ({result['rerank_error']}). Production answers from these "
            f"{len(result['reranked'])} unranked node(s), as below."
        )
    else:
        print(f"\nRERANKED ({len(result['reranked'])} kept at >= {result['min_score']})")
    print(header)
    for i, (score, meta) in enumerate(result["reranked"], 1):
        print(_row(i, score, meta))

    failed = False
    if result["dropped"]:
        print(f"\nSECURITY: the audience guard dropped {result['dropped']} node(s). See the ERROR log.")
        failed = True
    if not result["reranked"]:
        print(f"\nEMPTY CONTEXT: nothing left to answer from (rerank cutoff >= {result['min_score']}).")

    if args.expect:
        # Same matching as the eval: slugs case-insensitively, URLs normalized.
        from evalset import Question, hit_rank

        target = args.expect.strip()
        is_url = target.lower().startswith(("http://", "https://"))
        expected = Question(
            id="cli", q=args.question, kind="answer",
            expect=() if is_url else (target.lower(),),
            expect_url=(target,) if is_url else (),
        )
        rank = hit_rank(expected, [meta for _, meta in result["reranked"]])
        print(f"\nexpect {target}: " + (f"rank {rank} after rerank" if rank else "not in reranked results"))
        failed = failed or rank is None or rank > 5
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
