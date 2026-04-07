import asyncio
import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from scholarly import scholarly

from google_scholar_web_search import (
    advanced_google_scholar_search,
    google_scholar_search,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

mcp = FastMCP("google-scholar")


@mcp.tool()
async def search_google_scholar_key_words(
    query: str, num_results: int = 5
) -> List[Dict[str, Any]]:
    """Search for articles on Google Scholar using key words.

    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)

    Returns:
        List of dictionaries containing article information
    """
    logging.info(f"Searching Google Scholar: query={query}, num_results={num_results}")
    try:
        results = await asyncio.to_thread(google_scholar_search, query, num_results)
        return results
    except Exception as e:
        return [{"error": f"Google Scholar search failed: {str(e)}"}]


@mcp.tool()
async def search_google_scholar_advanced(
    query: str,
    author: Optional[str] = None,
    year_range: Optional[tuple] = None,
    num_results: int = 5,
) -> List[Dict[str, Any]]:
    """Search for articles on Google Scholar using advanced filters.

    Args:
        query: General search query
        author: Author name
        year_range: tuple containing (start_year, end_year)
        num_results: Number of results to return (default: 5)

    Returns:
        List of dictionaries containing article information
    """
    logging.info(f"Advanced Google Scholar search: {locals()}")
    try:
        results = await asyncio.to_thread(
            advanced_google_scholar_search, query, author, year_range, num_results
        )
        return results
    except Exception as e:
        return [{"error": f"Advanced search failed: {str(e)}"}]


@mcp.tool()
async def get_author_info(author_name: str) -> Dict[str, Any]:
    """Get detailed information about an author from Google Scholar.

    Args:
        author_name: Name of the author to search for

    Returns:
        Dictionary containing author information
    """
    logging.info(f"Retrieving author info for: {author_name}")
    try:
        search_query = scholarly.search_author(author_name)
        author = await asyncio.to_thread(next, search_query)
        filled_author = await asyncio.to_thread(scholarly.fill, author)
        return {
            "name": filled_author.get("name", "N/A"),
            "affiliation": filled_author.get("affiliation", "N/A"),
            "interests": filled_author.get("interests", []),
            "citedby": filled_author.get("citedby", 0),
            "publications": [
                {
                    "title": pub.get("bib", {}).get("title", "N/A"),
                    "year": pub.get("bib", {}).get("pub_year", "N/A"),
                    "citations": pub.get("num_citations", 0),
                }
                for pub in filled_author.get("publications", [])[:5]
            ],
        }
    except Exception as e:
        return {"error": f"Author info retrieval failed: {str(e)}"}


if __name__ == "__main__":
    mcp.run()
