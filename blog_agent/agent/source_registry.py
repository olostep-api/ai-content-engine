"""Source tracking helpers used by the blog writer workflow."""

from dataclasses import dataclass, field
from typing import Any

from blog_agent.models import ResearchSource

SOURCE_EXCERPT_LIMIT = 2500


@dataclass
class SourceRegistry:
    """Track research sources and search metadata during a writer run.

    The registry keeps the in-flight source list deduplicated by URL and
    preserves the last known search snippet for each source so later scrape
    results can enrich the same record.
    """

    sources_by_url: dict[str, ResearchSource] = field(default_factory=dict)
    search_index: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_sources(cls, sources: list[ResearchSource]) -> "SourceRegistry":
        """Create a registry preloaded with existing sources.

        Args:
            sources: Seed sources already available to the workflow.

        Returns:
            A registry populated with the provided sources.
        """
        registry = cls()
        registry.seed(sources)
        return registry

    def seed(self, sources: list[ResearchSource]) -> None:
        """Load existing sources into the registry.

        Args:
            sources: Sources to copy into the registry.
        """
        for source in sources:
            if source.url:
                self.upsert(
                    source.url,
                    title=source.title,
                    snippet=source.snippet,
                    content=source.content_excerpt,
                )

    def upsert(
        self,
        url: str,
        *,
        title: str = "",
        snippet: str = "",
        content: str = "",
    ) -> None:
        """Insert or update a source entry keyed by URL.

        Args:
            url: Canonical source URL.
            title: Source title if known.
            snippet: Search snippet or summary text.
            content: Extracted page content.
        """
        normalized_url = url.strip()
        if not normalized_url:
            return

        existing = self.sources_by_url.get(normalized_url)
        if existing is None:
            self.sources_by_url[normalized_url] = ResearchSource(
                title=title.strip() or normalized_url,
                url=normalized_url,
                snippet=snippet.strip(),
                content_excerpt=content[:SOURCE_EXCERPT_LIMIT],
            )
            return

        self.sources_by_url[normalized_url] = ResearchSource(
            title=title.strip() or existing.title,
            url=normalized_url,
            snippet=snippet.strip() or existing.snippet,
            content_excerpt=content[:SOURCE_EXCERPT_LIMIT] or existing.content_excerpt,
        )

    def record_search_results(self, results: list[dict[str, Any]]) -> None:
        """Store search result metadata and create source stubs.

        Args:
            results: Search result dictionaries returned by the web tool.
        """
        for item in results:
            if not isinstance(item, dict):
                continue

            url = str(item.get("url", "")).strip()
            if not url:
                continue

            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            self.search_index[url] = {"title": title, "snippet": snippet}
            self.upsert(url, title=title, snippet=snippet)

    def record_scrape_result(self, url: str, result: dict[str, Any]) -> None:
        """Merge scraped page content into the tracked source entry.

        Args:
            url: Source URL that was scraped.
            result: Scrape response payload returned by the tool.
        """
        metadata = self.search_index.get(url, {})
        self.upsert(
            url,
            title=str(result.get("title") or metadata.get("title", "")).strip(),
            snippet=str(metadata.get("snippet", "")).strip(),
            content=str(result.get("content") or ""),
        )

    def current_sources(self) -> list[ResearchSource]:
        """Return the current source list in insertion order."""
        return list(self.sources_by_url.values())
