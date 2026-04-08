"""Web page scrape tool for the blog writing workflow."""

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


def _build_scrape_payload(url: str) -> dict[str, Any]:
    """Build the Olostep scrape payload.

    Args:
        url: Page URL to scrape.

    Returns:
        Request body for the Scrapes endpoint.
    """
    return {
        "url_to_scrape": url,
        "formats": ["markdown"],
        "remove_css_selectors": "default",
        "transformer": "postlight",
    }


def _parse_scrape_result(body: dict[str, Any] | None, url: str) -> dict[str, str | None]:
    """Normalize the external scrape response.

    Args:
        body: Parsed JSON response from Olostep.
        url: URL that was scraped.

    Returns:
        A normalized scrape result dictionary.
    """
    if not isinstance(body, dict):
        return {"url": url, "title": "", "content": "", "error": "Invalid scrape response"}

    result = body.get("result", {})
    if not isinstance(result, dict):
        return {"url": url, "title": "", "content": "", "error": "Invalid scrape response"}

    page_metadata = result.get("page_metadata", {})
    if not isinstance(page_metadata, dict):
        page_metadata = {}

    content = result.get("markdown_content") or result.get("text_content") or ""
    return {
        "url": url,
        "title": page_metadata.get("title", ""),
        "content": content,
        "error": None,
    }


async def scrape_page(url: str) -> dict[str, str | None]:
    """Scrape a page and return its cleaned content.

    Args:
        url: Page URL to scrape.

    Returns:
        A dictionary containing the URL, title, content, and error.
    """
    logger.info("scrape_page called | url=%r", url)
    body, error = await post_json(
        "/scrapes",
        _build_scrape_payload(url),
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

    return _parse_scrape_result(body, url)
