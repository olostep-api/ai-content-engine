"""Low-level HTTP client for the Olostep API."""

import logging
import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.olostep.com/v1"
MISSING_API_KEY_ERROR = "OLOSTEP_API_KEY is not configured."


def _build_endpoint(path: str) -> str:
    """Build a full Olostep API endpoint URL."""
    return os.getenv("OLOSTEP_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + path


def _build_headers(api_key: str) -> dict[str, str]:
    """Build authorization headers for Olostep requests."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def post_json(
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    logger: logging.Logger,
    failure_message: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """POST JSON to Olostep and return the parsed body.

    Args:
        path: API path to append to the configured base URL.
        payload: JSON request body.
        timeout: Request timeout in seconds.
        logger: Logger used for error reporting.
        failure_message: Message to log if the request fails.

    Returns:
        A tuple containing the parsed response body or an error message.
    """
    api_key = os.getenv("OLOSTEP_API_KEY")
    if not api_key:
        return None, MISSING_API_KEY_ERROR

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(_build_endpoint(path), json=payload, headers=_build_headers(api_key))
            response.raise_for_status()
        body = response.json()
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        logger.exception(failure_message)
        return None, str(exc)

    if isinstance(body, dict):
        return body, None
    return {}, None
