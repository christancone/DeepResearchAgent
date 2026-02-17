from .base import SearchItem, WebSearchEngine

# Core search engines (always available)
from .bing_search import BingSearchEngine
from .ddg_search import DuckDuckGoSearchEngine
from .google_search import GoogleSearchEngine

# Optional search engines (may have extra dependencies)
try:
    from .baidu_search import BaiduSearchEngine
except ImportError:
    BaiduSearchEngine = None

try:
    from .firecrawl_search import FirecrawlSearchEngine
except ImportError:
    FirecrawlSearchEngine = None


__all__ = [
    "BaiduSearchEngine",
    "BingSearchEngine",
    "GoogleSearchEngine",
    "DuckDuckGoSearchEngine",
    "SearchItem",
    "WebSearchEngine",
    "FirecrawlSearchEngine"
]
