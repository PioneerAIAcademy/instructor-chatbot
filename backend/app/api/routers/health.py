import logging
import os

from fastapi import APIRouter
from pinecone import Pinecone
from app.langfuse import langfuse

health_router = APIRouter()
logger = logging.getLogger("uvicorn")


@health_router.get("/health")
async def liveness():
    """Basic liveness check — confirms the server is running."""
    return {"status": "ok"}


@health_router.get("/health/ready")
async def readiness():
    """Readiness check — confirms all dependencies are reachable."""
    checks = {}

    # Check Pinecone — describe_index makes a real network call to Pinecone
    try:
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        pc.describe_index(os.getenv("PINECONE_INDEX_NAME"))
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
    # Public response is intentionally coarse (no per-dependency detail).
    return {"status": "ok" if all_ok else "degraded"}
