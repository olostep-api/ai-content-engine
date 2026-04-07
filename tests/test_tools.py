from __future__ import annotations

import asyncio

from blog_agent.tools import scrape, search
from blog_agent.tools.tools import ToolProvider


def test_tool_provider_emits_events_on_success() -> None:
    asyncio.run(_test_tool_provider_emits_events_on_success())


async def _test_tool_provider_emits_events_on_success() -> None:
    events: list[tuple[str, dict]] = []
    provider = ToolProvider(on_event=lambda event_type, data: _capture(events, event_type, data))

    async def fake_call() -> dict:
        return {"ok": True}

    result = await provider._run_tool("search_web", {"query": "x"}, fake_call())

    assert result == {"ok": True}
    assert [name for name, _ in events] == ["searching", "tool_started", "tool_completed"]


def test_tool_provider_returns_error_on_timeout() -> None:
    asyncio.run(_test_tool_provider_returns_error_on_timeout())


async def _test_tool_provider_returns_error_on_timeout() -> None:
    provider = ToolProvider(timeout_seconds=0)

    async def slow_call() -> dict:
        return {"ok": True}

    result = await provider._run_tool("scrape_page", {"url": "https://example.com"}, slow_call())
    assert "error" in result


async def _capture(events: list[tuple[str, dict]], event_type: str, data: dict) -> None:
    events.append((event_type, data))


def test_search_web_preserves_success_shape() -> None:
    asyncio.run(_test_search_web_preserves_success_shape())


async def _test_search_web_preserves_success_shape() -> None:
    async def fake_post_json(*args, **kwargs):
        return (
            {
                "result": {
                    "json_content": {
                        "results": [
                            {"title": "One", "url": "https://example.com/1", "snippet": "First"},
                            {"title": "Two", "url": "https://example.com/2", "snippet": "Second"},
                        ]
                    }
                }
            },
            None,
        )

    original = search.post_json
    search.post_json = fake_post_json
    try:
        result = await search.search_web("ai agents", top_k=1)
    finally:
        search.post_json = original

    assert result == {
        "query": "ai agents",
        "results": [
            {"title": "One", "url": "https://example.com/1", "snippet": "First"},
        ],
        "error": None,
    }


def test_search_web_preserves_error_shape() -> None:
    asyncio.run(_test_search_web_preserves_error_shape())


async def _test_search_web_preserves_error_shape() -> None:
    async def fake_post_json(*args, **kwargs):
        return None, "boom"

    original = search.post_json
    search.post_json = fake_post_json
    try:
        result = await search.search_web("ai agents", top_k=3)
    finally:
        search.post_json = original

    assert result == {"query": "ai agents", "results": [], "error": "boom"}


def test_scrape_page_preserves_success_shape() -> None:
    asyncio.run(_test_scrape_page_preserves_success_shape())


async def _test_scrape_page_preserves_success_shape() -> None:
    async def fake_post_json(*args, **kwargs):
        return (
            {
                "result": {
                    "page_metadata": {"title": "Example"},
                    "markdown_content": "# Hello",
                }
            },
            None,
        )

    original = scrape.post_json
    scrape.post_json = fake_post_json
    try:
        result = await scrape.scrape_page("https://example.com")
    finally:
        scrape.post_json = original

    assert result == {
        "url": "https://example.com",
        "title": "Example",
        "content": "# Hello",
        "error": None,
    }


def test_scrape_page_preserves_error_shape() -> None:
    asyncio.run(_test_scrape_page_preserves_error_shape())


async def _test_scrape_page_preserves_error_shape() -> None:
    async def fake_post_json(*args, **kwargs):
        return None, "boom"

    original = scrape.post_json
    scrape.post_json = fake_post_json
    try:
        result = await scrape.scrape_page("https://example.com")
    finally:
        scrape.post_json = original

    assert result == {
        "url": "https://example.com",
        "title": "",
        "content": "",
        "error": "boom",
    }
