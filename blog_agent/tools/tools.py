"""Shared tool adapter layer for the blog writing workflow."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from blog_agent.tools import scrape, search
from blog_agent.models import EventType

ToolEventCallback = Callable[[EventType | str, dict[str, Any]], Awaitable[None]]


@dataclass
class ToolProvider:
    """Execute tools with timeout and lifecycle event emission."""

    on_event: ToolEventCallback | None = None
    timeout_seconds: int = 60

    async def search_web(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """Run the web search tool.

        Args:
            query: Search query to send to the tool.
            top_k: Maximum number of results to request.

        Returns:
            Normalized search results or an error payload.
        """
        return await self._run_tool("search_web", {"query": query, "top_k": top_k}, search.search_web(query, top_k))

    async def scrape_page(self, url: str) -> dict[str, str | None]:
        """Run the page scrape tool.

        Args:
            url: Page URL to scrape.

        Returns:
            Normalized scrape results or an error payload.
        """
        return await self._run_tool("scrape_page", {"url": url}, scrape.scrape_page(url))

    async def _run_tool(
        self,
        name: str,
        payload: dict[str, Any],
        tool_call: Awaitable[dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute a tool call with timeout handling and events.

        Args:
            name: Tool name used for lifecycle events.
            payload: Tool input payload.
            tool_call: Awaitable tool execution.

        Returns:
            Tool result payload, or an error dictionary if execution failed.
        """
        if self.on_event:
            if name == "search_web":
                await self.on_event(EventType.SEARCHING, payload)
            await self.on_event(EventType.TOOL_STARTED, {"tool": name, **payload})
        try:
            tool_result = await asyncio.wait_for(tool_call, timeout=self.timeout_seconds)
        except Exception as exc:
            tool_result = {"error": str(exc)}
        if self.on_event:
            await self.on_event(EventType.TOOL_COMPLETED, {"tool": name, "result": tool_result})
        return tool_result


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return the tool schemas exposed to the agent."""
    return [search.SEARCH_TOOL_DEFINITION, scrape.SCRAPE_TOOL_DEFINITION]
