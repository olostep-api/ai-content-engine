"""Web search tool for the blog writing workflow."""

import json
import logging
from typing import Any

from blog_agent.tools.olostep import post_json

logger = logging.getLogger(__name__)


SEARCH_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for relevant pages and return the best matching results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The web search query."},
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def _build_search_payload(query: str, top_k: int) -> dict[str, Any]:
    """Build the Olostep Answers payload for a web search.

    Args:
        query: Search query to send to the external API.
        top_k: Maximum number of results to request.

    Returns:
        Request body for the Answers endpoint.
    """
    return {
        "task": (
            f"Return the top {top_k} most relevant web pages for this blog research query: {query}. "
            "For each result, provide title, url, and a short snippet."
        ),
        "json_format": {
            "results": [{"title": "", "url": "", "snippet": ""}],
        },
    }


def _parse_search_results(body: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize the external API response into search result records.

    Args:
        body: Parsed JSON response from Olostep.

    Returns:
        A normalized list of result dictionaries.
    """
    if not isinstance(body, dict):
        return []

    result_payload = body.get("result", {})
    json_blob = result_payload.get("json_content", result_payload)
    parsed: dict[str, Any]
    if isinstance(json_blob, str):
        try:
            parsed = json.loads(json_blob)
        except json.JSONDecodeError:
            parsed = {}
    elif isinstance(json_blob, dict):
        parsed = json_blob
    else:
        parsed = {}

    results = parsed.get("results", [])
    if not isinstance(results, list):
        return []

    normalized_results: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized_results.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
            }
        )
    return normalized_results


async def search_web(query: str, top_k: int = 5) -> dict[str, Any]:
    """Search the web and return normalized results.

    Args:
        query: Search query to run.
        top_k: Maximum number of results to return.

    Returns:
        A dictionary containing the query, normalized results, and any error.
    """
    logger.info("search_web called | query=%r top_k=%s", query, top_k)
    body, error = await post_json(
        "/answers",
        _build_search_payload(query, top_k),
        timeout=45,
        logger=logger,
        failure_message="Olostep search failed",
    )
    if error:
        return {"query": query, "results": [], "error": error}

    normalized = _parse_search_results(body)[:top_k]
    return {"query": query, "results": normalized, "error": None}
