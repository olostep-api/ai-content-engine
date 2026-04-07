from __future__ import annotations

import logging
from typing import Any

from blog_agent.tools.olostep import post_json

logger = logging.getLogger(__name__)


SCRAPE_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "scrape_page",
        "description": (
            "Scrape the full text content of a web page given its URL. "
            "Use this after search_web to extract detailed information from "
            "the most promising links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to scrape.",
                },
            },
            "required": ["url"],
        },
    },
}


async def scrape_page(url: str) -> dict[str, str | None]:
    """
    Scrape a web page and return its cleaned text content.
    """
    logger.info("scrape_page called | url=%r", url)
    payload = {
        "url_to_scrape": url,
        "formats": ["markdown"],
        "remove_css_selectors": "default",
        "transformer": "postlight",
    }
    body, error = await post_json(
        "/scrapes",
        payload,
        timeout=60,
        logger=logger,
        failure_message="Olostep scrape failed",
    )
    if error:
        return {
            "url": url,
            "title": "",
            "content": "",
            "error": error,
        }

    result = body.get("result", {})
    page_metadata = result.get("page_metadata", {})
    content = result.get("markdown_content") or result.get("text_content") or ""
    return {
        "url": url,
        "title": page_metadata.get("title", ""),
        "content": content,
        "error": None,
    }
