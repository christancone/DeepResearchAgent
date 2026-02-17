import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv(verbose=True)

# Try to import DocumentConverterResult from markitdown, fallback to local dataclass
try:
    from markitdown._base_converter import DocumentConverterResult
except ImportError:
    @dataclass
    class DocumentConverterResult:
        """Fallback dataclass when markitdown is not available."""
        markdown: str = ""
        title: str = ""

# Optional imports for web crawling
try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    AsyncWebCrawler = None
    CRAWL4AI_AVAILABLE = False

try:
    from firecrawl import FirecrawlApp
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FirecrawlApp = None
    FIRECRAWL_AVAILABLE = False


async def firecrawl_fetch_url(url: str):
    if not FIRECRAWL_AVAILABLE:
        return None
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY", None))

        response = app.scrape_url(
            url,
        )

        result = response.markdown

        return result
    except Exception as e:
        return None

async def fetch_crawl4ai_url(url: str):
    """Fetch content from a given URL using the crawl4ai library."""
    if not CRAWL4AI_AVAILABLE:
        return None
    try:
        async with AsyncWebCrawler() as crawler:
            response = await crawler.arun(
                url=url,
            )

            if response:
                result = response.markdown
                return result
            else:
                return None
    except Exception as e:
        return None

async def fetch_url(url: str) -> Optional[DocumentConverterResult]:
    # Fetch content from a URL using Firecrawl and Crawl4AI.

    try:
        firecrawl_result = await firecrawl_fetch_url(url)

        if firecrawl_result:
            return DocumentConverterResult(
                markdown=firecrawl_result,
                title=f"Fetched content from {url}",
            )

        crawl4ai_result = await fetch_crawl4ai_url(url)
        if crawl4ai_result:
            return DocumentConverterResult(
                markdown=crawl4ai_result,
                title=f"Fetched content from {url}",
            )

    except Exception as e:
        return None

if __name__ == '__main__':
    import asyncio
    url = "https://www.google.com/"
    result = asyncio.run(firecrawl_fetch_url(url))
    print(result)