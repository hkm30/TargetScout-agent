import logging
from scholarly import scholarly, ProxyGenerator

logger = logging.getLogger(__name__)

# Set up free proxy rotation to avoid Google blocking cloud IPs
_proxy_initialized = False


def _ensure_proxy():
    """Initialize free proxy on first use."""
    global _proxy_initialized
    if not _proxy_initialized:
        try:
            pg = ProxyGenerator()
            pg.FreeProxies()
            scholarly.use_proxy(pg)
            logger.info("Free proxy initialized for scholarly")
        except Exception as e:
            logger.warning("Failed to initialize proxy, using direct connection: %s", e)
        _proxy_initialized = True


def google_scholar_search(query, num_results=5):
    """Search Google Scholar using the scholarly library."""
    _ensure_proxy()
    results = []
    try:
        search_query = scholarly.search_pubs(query)
        for _ in range(num_results):
            try:
                pub = next(search_query)
                bib = pub.get("bib", {})
                results.append({
                    "Title": bib.get("title", "N/A"),
                    "Authors": ", ".join(bib.get("author", [])) if isinstance(bib.get("author"), list) else bib.get("author", "N/A"),
                    "Abstract": bib.get("abstract", "No abstract available"),
                    "URL": pub.get("pub_url") or pub.get("eprint_url") or "N/A",
                    "Year": bib.get("pub_year", "N/A"),
                    "Citations": pub.get("num_citations", 0),
                })
            except StopIteration:
                break
    except Exception as e:
        logger.error("Google Scholar search failed: %s", e)
        return [{"error": f"Google Scholar search failed: {str(e)}"}]
    return results


def advanced_google_scholar_search(query, author=None, year_range=None, num_results=5):
    """Search Google Scholar using advanced filters via scholarly library."""
    _ensure_proxy()

    # Build the query string with filters
    search_query_str = query
    if author:
        search_query_str += f" author:{author}"

    results = []
    try:
        search_query = scholarly.search_pubs(search_query_str)
        for _ in range(num_results):
            try:
                pub = next(search_query)
                bib = pub.get("bib", {})

                # Filter by year range if specified
                if year_range:
                    pub_year = bib.get("pub_year", "")
                    if pub_year:
                        try:
                            year = int(pub_year)
                            if year < year_range[0] or year > year_range[1]:
                                continue
                        except (ValueError, TypeError):
                            pass

                results.append({
                    "Title": bib.get("title", "N/A"),
                    "Authors": ", ".join(bib.get("author", [])) if isinstance(bib.get("author"), list) else bib.get("author", "N/A"),
                    "Abstract": bib.get("abstract", "No abstract available"),
                    "URL": pub.get("pub_url") or pub.get("eprint_url") or "N/A",
                    "Year": bib.get("pub_year", "N/A"),
                    "Citations": pub.get("num_citations", 0),
                })
            except StopIteration:
                break
    except Exception as e:
        logger.error("Advanced Google Scholar search failed: %s", e)
        return [{"error": f"Advanced search failed: {str(e)}"}]
    return results
