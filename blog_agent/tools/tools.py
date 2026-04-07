from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from blog_agent.tools import scrape, search

ToolEventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ToolProvider:
    on_event: ToolEventCallback | None = None
    timeout_seconds: int = 60

    async def search_web(self, query: str, top_k: int = 5) -> dict[str, Any]:
        return await self._run_tool("search_web", {"query": query, "top_k": top_k}, search.search_web(query, top_k))

    async def scrape_page(self, url: str) -> dict[str, str | None]:
        return await self._run_tool("scrape_page", {"url": url}, scrape.scrape_page(url))

    async def _run_tool(
        self,
        name: str,
        payload: dict[str, Any],
        call: Awaitable[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.on_event:
            if name == "search_web":
                await self.on_event("searching", payload)
            await self.on_event("tool_started", {"tool": name, **payload})
        try:
            result = await asyncio.wait_for(call, timeout=self.timeout_seconds)
        except Exception as exc:
            result = {"error": str(exc)}
        if self.on_event:
            await self.on_event("tool_completed", {"tool": name, "result": result})
        return result


def get_tool_definitions() -> list[dict[str, Any]]:
    return [search.SEARCH_TOOL_DEFINITION, scrape.SCRAPE_TOOL_DEFINITION]
