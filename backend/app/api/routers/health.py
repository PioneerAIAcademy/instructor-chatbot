import logging
import os

from fastapi import APIRouter
from pinecone import Pinecone
from app.engine.audience_guard import IndexConfigError, check_index_config
from app.langfuse import langfuse

health_router = APIRouter()
logger = logging.getLogger("uvicorn")


@health_router.get("/health")
async def liveness():
    """Basic liveness check — confirms the server is running."""
    return {"status": "ok"}


@health_router.get("/health/ready")
async def readiness():
    """Readiness check — confirms all dependencies are reachable.

    Also reports which index this deployment answers from and whether the
    audience index guard accepts its config (CLAUDE.md §7 Phase 1). The
    index name is not a secret; keys and hosts are never returned.
    """
    checks = {}

    index_name = os.getenv("PINECONE_INDEX_NAME", "")
    try:
        check_index_config()
        guard = "ok"
    except IndexConfigError as e:
        logger.error(f"Index guard refused config: {e}")
        guard = "error"
    checks["guard"] = guard

    # Check Pinecone — describe_index makes a real network call to Pinecone.
    # Skipped when the guard refused the index: never touch the wrong one.
    if guard != "ok":
        checks["pinecone"] = "skipped"
    else:
        try:
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            pc.describe_index(index_name)
            checks["pinecone"] = "ok"
        except Exception as e:
            logger.error(f"Pinecone health check failed: {e}")
            checks["pinecone"] = "error"

    # Check Langfuse — auth_check() returns True/False, does not raise on failure
    try:
        ok = langfuse.auth_check()
        checks["langfuse"] = "ok" if ok else "error"
    except Exception as e:
        logger.error(f"Langfuse health check failed: {e}")
        checks["langfuse"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        # Keep the per-service breakdown in server logs only — exposing which
        # specific backing service is down aids reconnaissance for anonymous callers.
        logger.warning(f"Readiness degraded: {checks}")
    # Public response is otherwise coarse (no per-dependency detail).
    return {
        "status": "ok" if all_ok else "degraded",
        "index": index_name,
        "guard": guard,
    }
