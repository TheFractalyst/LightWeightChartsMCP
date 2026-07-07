# ruff: noqa: E501
"""
pipeline/scrape_lwc.py
Scrape TradingView Lightweight Charts documentation from sitemap.

Direct HTTP requests (github.io is reliable, no ScraperAPI needed).
Covers all 5 versions (3.8, 4.0, 4.1, 4.2, 5.0) + tutorials.

Usage:
    python pipeline/scrape_lwc.py [--limit N] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<8} | {message}", level="INFO")

ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT = ROOT / "data" / "lwc_entries.json"
SITEMAP_URL = "https://tradingview.github.io/lightweight-charts/sitemap.xml"
DOCS_BASE = "https://tradingview.github.io/lightweight-charts"
DELAY = 0.3

KNOWN_VERSIONS = {"3.8", "4.0", "4.1", "4.2", "5.0"}


def fetch_sitemap(client: httpx.Client) -> list[str]:
    """Fetch and parse the sitemap."""
    logger.info(f"Fetching sitemap: {SITEMAP_URL}")
    resp = client.get(SITEMAP_URL, timeout=30)
    resp.raise_for_status()

    urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
    urls = [u.strip() for u in urls if "tradingview.github.io/lightweight-charts" in u]

    # Filter out search page
    urls = [u for u in urls if "/search" not in u]

    logger.info(f"Found {len(urls)} URLs in sitemap")
    return urls


def infer_version(url: str) -> str:
    """Infer version from URL path."""
    path = urlparse(url).path
    parts = path.replace("/lightweight-charts/", "").split("/")

    if len(parts) >= 2 and parts[0] == "docs":
        ver = parts[1]
        if ver in KNOWN_VERSIONS:
            return ver

    if "/tutorials/" in path or path.endswith("/tutorials"):
        return "tutorials"

    return "latest"


def infer_namespace(url: str) -> str:
    """Infer namespace from URL path."""
    path = urlparse(url).path

    # API namespaces
    for ns in ("enumerations", "functions", "interfaces", "type-aliases", "variables"):
        if f"/api/{ns}/" in path:
            return ns

    # Guide namespaces
    if "/docs/" in path:
        parts = path.replace("/lightweight-charts/docs/", "").split("/")
        if len(parts) >= 2:
            section = parts[1] if parts[0] in KNOWN_VERSIONS else parts[0]
            if section in ("android", "ios", "price-scale", "release-notes",
                          "series-types", "time-scale", "time-zones", "migrations",
                          "plugins"):
                return section
            if section == "api":
                return "functions"
            return "getting-started"

    # Tutorial namespaces
    if "/tutorials/" in path:
        parts = path.replace("/lightweight-charts/tutorials/", "").split("/")
        if parts:
            if parts[0] in ("customization", "a11y", "react", "vuejs", "webcomponents"):
                return parts[0]
            if parts[0] == "how_to":
                return "how-to"
            if parts[0] == "demos":
                return "demos"
            return parts[0]

    return "general"


def infer_category(url: str, content: str) -> str:
    """Infer entry category from URL and content."""
    path = urlparse(url).path

    if "/api/enumerations/" in path:
        return "enumeration"
    if "/api/functions/" in path:
        return "function"
    if "/api/interfaces/" in path:
        return "interface"
    if "/api/type-aliases/" in path:
        return "type-alias"
    if "/api/variables/" in path:
        return "variable"
    if "/api" in path:
        return "function"
    if "/tutorials/" in path:
        return "tutorial"
    if "/migrations/" in path:
        return "guide"
    if "/plugins/" in path:
        return "guide"

    return "guide"


def extract_name(url: str, soup: BeautifulSoup) -> str:
    """Extract entry name from URL and page content."""
    path = urlparse(url).path
    parts = path.split("/")

    # Try to get name from the last path segment
    for part in reversed(parts):
        if part and part not in ("api", "docs", "tutorials", "enumerations",
                                  "functions", "interfaces", "type-aliases",
                                  "variables", "migrations", "plugins"):
            name = part.replace("-", " ").replace("_", " ").strip()
            if name:
                return name

    # Fallback: try h1 from soup
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    return "Lightweight Charts"


def extract_description(soup: BeautifulSoup) -> str:
    """Extract first meaningful paragraph as description."""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 30 and not text.startswith("[") and not text.startswith("Note:"):
            return text[:500]
    return ""


def extract_syntax(soup: BeautifulSoup) -> str:
    """Extract syntax/signature from code blocks."""
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        text = code.get_text(strip=True) if code else pre.get_text(strip=True)
        if text and ("(" in text or "=>" in text or "interface " in text or "type " in text):
            return text[:300]
    return ""


def extract_examples(soup: BeautifulSoup) -> list[str]:
    """Extract code examples from the page."""
    examples = []
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        text = code.get_text() if code else pre.get_text()
        text = text.strip()
        if text and len(text) > 20:
            examples.append(text)
    return examples[:5]


def parse_page(html: str, url: str) -> dict[str, Any]:
    """Parse an HTML page into a structured entry."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style tags
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    return {
        "name": extract_name(url, soup),
        "version": infer_version(url),
        "namespace": infer_namespace(url),
        "category": infer_category(url, soup.get_text()),
        "syntax": extract_syntax(soup),
        "description": extract_description(soup),
        "parameters": [],
        "examples": extract_examples(soup),
        "url": url,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def scrape(output: Path, limit: int | None = None) -> None:
    """Scrape Lightweight Charts docs and save entries to JSON."""
    output.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    errors = 0

    with httpx.Client(timeout=30, headers={"User-Agent": "LWC-MCP-Scraper/1.0"}) as client:
        urls = fetch_sitemap(client)
        if limit:
            urls = urls[:limit]
            logger.info(f"Limited to {limit} URLs")

        for url in tqdm(urls, desc="Scraping Lightweight Charts"):
            try:
                resp = client.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"Failed: {url} ({resp.status_code})")
                    errors += 1
                    continue

                entry = parse_page(resp.text, url)
                entries.append(entry)

                time.sleep(DELAY)
            except Exception as e:
                logger.warning(f"Error scraping {url}: {e}")
                errors += 1

    logger.info(f"Scraped {len(entries)} entries ({errors} errors)")
    output.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved to {output}")

    from collections import Counter
    ver_counts = Counter(e.get("version", "unknown") for e in entries)
    cat_counts = Counter(e.get("category", "unknown") for e in entries)
    ns_counts = Counter(e.get("namespace", "unknown") for e in entries)

    logger.info("Versions:")
    for ver, n in sorted(ver_counts.items()):
        logger.info(f"  {ver:<10} {n:>5}")
    logger.info("Categories:")
    for cat, n in sorted(cat_counts.items()):
        logger.info(f"  {cat:<15} {n:>5}")
    logger.info("Namespaces:")
    for ns, n in sorted(ns_counts.items()):
        logger.info(f"  {ns:<20} {n:>5}")


def main():
    parser = argparse.ArgumentParser(description="Scrape TradingView Lightweight Charts documentation")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Output file (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of URLs to scrape")
    args = parser.parse_args()

    scrape(args.output, args.limit)


if __name__ == "__main__":
    main()
