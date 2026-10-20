"""ALLOWED_ORIGINS tolerates a trailing slash (browsers never send one)."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PROBE = """
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
for origin in ("http://localhost:3000", "http://evil.example"):
    r = client.options(
        "/api/v1/chat",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    print(origin, r.status_code)
"""


def test_trailing_slash_in_allowed_origins_still_matches():
    env = {
        **os.environ,
        "ALLOWED_ORIGINS": "http://localhost:3000/",
        "CORS_ALLOW_ALL": "false",
    }
    out = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert "http://localhost:3000 200" in out.stdout
    assert "http://evil.example 400" in out.stdout
