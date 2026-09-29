from __future__ import annotations

from langchain.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the public web for current information. Use for news, facts,
    documentation, and anything after the model's training cutoff.
    Returns titles, URLs, and snippets. Cite URLs in the final answer."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "duckduckgo-search is not installed. pip install duckduckgo-search"

    rows = []
    with DDGS() as ddgs:
        for hit in ddgs.text(query, max_results=5):
            rows.append(
                f"- {hit.get('title')}\n  {hit.get('href')}\n  {hit.get('body')}"
            )
    return "\n".join(rows) if rows else f"no results for: {query}"
