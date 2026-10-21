"""CORS: ALLOWED_ORIGINS tolerates a trailing slash (browsers never send one),
and explicit ENVIRONMENT=dev also allows any localhost port."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PROBE = """
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
for origin in ("http://localhost:3000", "http://localhost:3001", "http://evil.example"):
    r = client.options(
        "/api/v1/chat",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    print(origin, r.status_code)
"""


def _probe(environment: str) -> str:
    # Placeholder settings only (as test_audience_guard._boot): the suite runs
    # keyless in CI and in the pre-push hook, with no backend/.env.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "MODEL_PROVIDER": "openai",
        "MODEL": "gpt-4o-mini",
        "EMBEDDING_MODEL": "text-embedding-3-large",
        "EMBEDDING_DIM": "3072",
        "OPENAI_API_KEY": "placeholder",
        "VOYAGE_API_KEY": "placeholder",
        "PINECONE_INDEX_NAME": "instructor-assistant",
        "PROMPT_INJECTION_ML_ENABLED": "false",
        "HF_HUB_OFFLINE": "1",
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
        "LANGFUSE_TRACING_ENABLED": "false",
        "ALLOWED_ORIGINS": "http://localhost:3000/",
        "CORS_ALLOW_ALL": "false",
        "ENVIRONMENT": environment,
    }
    out = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout


def test_trailing_slash_in_allowed_origins_still_matches():
    out = _probe("prod")
    assert "http://localhost:3000 200" in out
    assert "http://evil.example 400" in out
    # Outside dev, only the listed origins: another localhost port is refused.
    assert "http://localhost:3001 400" in out


def test_explicit_dev_allows_any_localhost_port():
    out = _probe("dev")
    assert "http://localhost:3000 200" in out
    assert "http://localhost:3001 200" in out
    assert "http://evil.example 400" in out
