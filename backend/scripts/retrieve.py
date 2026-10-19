"""Raw and reranked retrieval for one question, through the production path.

    poetry run python scripts/retrieve.py "When do instructors get paid?"
    poetry run python scripts/retrieve.py "..." --expect pay-dates-for-worldwide-online-instructors-ia

LIVE AND BILLABLE: one OpenAI query embedding, one Pinecone query, one Voyage
rerank. Uses the same index guard, filter, retriever (top 35), audience
postprocessor, and rerank settings (rerank-lite-1, top 17, >= 0.21) as
/api/v1/chat. No LLM answer is generated. Read-only against Pinecone.

Prints the index, then every raw and reranked node's slug, source, role, and
score. With --expect, reports the expected slug's rank after rerank and exits
1 if it isn't in the top 5 (or the guard dropped anything). Never prints keys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# The project is not installed as a package; put backend/ on the path.
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")


def _row(rank: int, score: float | None, metadata: dict) -> str:
    title = (metadata.get("title") or "")[:48]
    score_txt = f"{score:.3f}" if isinstance(score, (int, float)) else "  -  "
    return (
        f"{rank:>3}  {score_txt}  {metadata.get('slug', '?'):<58}  "
        f"{metadata.get('source', '?'):<28}  {metadata.get('role', '?'):<10}  {title}"
    )


def run_retrieval(question: str) -> dict:
    """Return {"index", "raw", "reranked", "dropped"} for one question.

    raw / reranked are lists of (score, metadata) in rank order. Reused by
    the Phase 2 retrieval eval.
    """
    from llama_index.core import QueryBundle

    from app.engine import get_chat_engine
    from app.engine.audience_guard import audience_guard_of, check_index_config, instructor_filters
    from app.engine.custom_condense_plus_context import (
        RERANK_MODEL,
        RERANK_TOP_K,
        _do_voyage_rerank,
    )
    from app.settings import init_settings

    index_name = check_index_config()
    init_settings()

    engine = get_chat_engine(filters=instructor_filters())
    raw_nodes = engine._retriever.retrieve(question)
    raw = [(n.score, dict(n.node.metadata)) for n in raw_nodes]

    nodes = raw_nodes
    for postprocessor in engine._node_postprocessors:
        nodes = postprocessor.postprocess_nodes(nodes, query_bundle=QueryBundle(question))
    guard = audience_guard_of(engine)
    dropped = guard.dropped if guard is not None else 0

    # Same call the engine makes (it reranks `NodeWithScore.text`): unique
    # texts in, kept texts out in rank order.
    by_text = {}
    for n in nodes:
        by_text.setdefault(n.text, n)
    kept_texts, scores, ok, exc = _do_voyage_rerank(
        question, list(by_text), RERANK_MODEL, RERANK_TOP_K
    )
    if not ok:
        raise RuntimeError(f"Voyage rerank failed: {exc!r}")
    reranked = [(scores.get(t), dict(by_text[t].node.metadata)) for t in kept_texts]

    return {"index": index_name, "raw": raw, "reranked": reranked, "dropped": dropped}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("question")
    parser.add_argument("--expect", help="slug that should rank in the top 5 after rerank")
    args = parser.parse_args()

    result = run_retrieval(args.question)
    header = f"{'#':>3}  {'score':<5}  {'slug':<58}  {'source':<28}  {'role':<10}  title"

    print(f"index: {result['index']}")
    print(f"question: {args.question}\n")
    print(f"RAW (filtered, top {len(result['raw'])})")
    print(header)
    for i, (score, meta) in enumerate(result["raw"], 1):
        print(_row(i, score, meta))

    print(f"\nRERANKED ({len(result['reranked'])} kept at >= 0.21)")
    print(header)
    for i, (score, meta) in enumerate(result["reranked"], 1):
        print(_row(i, score, meta))

    failed = False
    if result["dropped"]:
        print(f"\nSECURITY: the audience guard dropped {result['dropped']} node(s). See the ERROR log.")
        failed = True
    if not result["reranked"]:
        print("\nEMPTY CONTEXT: rerank kept nothing at >= 0.21.")

    if args.expect:
        slugs = [meta.get("slug") for _, meta in result["reranked"]]
        rank = slugs.index(args.expect) + 1 if args.expect in slugs else None
        print(f"\nexpect {args.expect}: " + (f"rank {rank} after rerank" if rank else "not in reranked results"))
        failed = failed or rank is None or rank > 5
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
