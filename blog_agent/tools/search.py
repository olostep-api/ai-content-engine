from __future__ import annotations

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


async def search_web(query: str, top_k: int = 5) -> dict[str, Any]:
    """
    Search the web using Olostep's Answers API and normalize the response.
    """
    logger.info("search_web called | query=%r top_k=%s", query, top_k)
    payload = {
        "task": (
            f"Return the top {top_k} most relevant web pages for this blog research query: {query}. "
            "For each result, provide title, url, and a short snippet."
        ),
        "json_format": {
            "results": [{"title": "", "url": "", "snippet": ""}],
        },
    }
    body, error = await post_json(
        "/answers",
        payload,
        timeout=45,
        logger=logger,
        failure_message="Olostep search failed",
    )
    if error:
        return {"query": query, "results": [], "error": error}

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
    normalized = []
    for item in results[:top_k]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
            }
        )

    return {"query": query, "results": normalized, "error": None}
