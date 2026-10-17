import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_valid_api_keys() -> set:
    """Load valid API keys from environment variable."""
    keys = os.getenv("API_KEYS", "")
    return {k.strip() for k in keys.split(",") if k.strip()}


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Validate the API key from the X-API-Key request header.
    - Only in an explicit ``ENVIRONMENT=dev`` with no keys configured: allows all requests.
    - Everywhere else: fail closed. A misconfigured deployment (missing ``ENVIRONMENT``
      or empty ``API_KEYS``) is rejected rather than left open.
    """
    # No default: an UNSET environment must not be treated as dev, otherwise a
    # deployment that forgets ENVIRONMENT would silently run fully open.
    environment = os.getenv("ENVIRONMENT")
    valid_keys = _get_valid_api_keys()

    # Dev convenience bypass — ONLY when dev is explicitly requested and no keys exist.
    if environment == "dev" and not valid_keys:
        return "dev"

    # Fail closed: outside explicit dev, an empty key set is a misconfiguration,
    # not a reason to allow everyone through.
    if not valid_keys:
        raise HTTPException(
            status_code=503,
            detail="Server authentication is not configured.",
        )

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized."
        )
    return api_key
