"""Article scraper — extracts clean text from news article URLs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
}

# Selectors tried in priority order, per domain pattern
_DOMAIN_SELECTORS: dict[str, list[str]] = {
    "bbc": [
        "[data-component='text-block']",
        ".ssrcss-uf6wea-RichTextComponentWrapper",
        "article p",
        "main p",
    ],
    "default": [
        "article p",
        "[itemprop='articleBody'] p",
        ".article-body p",
        ".story-body p",
        ".post-content p",
        ".entry-content p",
        "main p",
    ],
}

# Classes that indicate noise — checked only on the element itself and its
# IMMEDIATE parent (not the full ancestor chain, to avoid false positives like
# "ContainerWithSidebarWrapper" that wrap the whole article body).
_NOISE_CLASSES = re.compile(
    r"\bnav\b|\bheader\b|\bfooter\b|\bcookie\b|\badvert\b|\bpromo\b|"
    r"\brelated\b|\bshare\b|\bsocial\b|\bcomment\b|\bcaption\b|\bcredit\b|"
    r"\bbyline\b|\btimestamp\b",
    re.I,
)


@dataclass
class ScrapedArticle:
    title: str
    text: str          # full article text joined with newlines
    paragraphs: list[str]
    url: str
    domain: str
    word_count: int


def _domain_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for key in _DOMAIN_SELECTORS:
        if key in host:
            return key
    return "default"


def _is_noise(tag: Tag) -> bool:
    """Check only the element itself and its immediate parent for noise markers."""
    own = " ".join(tag.get("class", [])) + " " + (tag.get("id") or "")
    if _NOISE_CLASSES.search(own):
        return True
    parent = tag.parent
    if parent and parent.name not in ("body", "[document]", None):
        parent_str = " ".join(parent.get("class", [])) + " " + (parent.get("id") or "")
        if _NOISE_CLASSES.search(parent_str):
            return True
    return False


def _extract_title(soup: BeautifulSoup) -> str:
    # Try OG title first, then h1, then <title>
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    title = soup.find("title")
    return title.get_text(strip=True) if title else ""


def _extract_paragraphs(soup: BeautifulSoup, domain_key: str) -> list[str]:
    selectors = _DOMAIN_SELECTORS.get(domain_key, _DOMAIN_SELECTORS["default"])

    for selector in selectors:
        elements = soup.select(selector)
        paragraphs = []
        for el in elements:
            text = el.get_text(separator=" ", strip=True)
            # Skip very short snippets and obvious noise
            if len(text) < 50:
                continue
            if _is_noise(el):
                continue
            # Clean up encoding artifacts and excessive whitespace
            text = re.sub(r"\s+", " ", text)
            text = text.replace("\u00e2\u0080\u0099", "'").replace("\u2019", "'")
            paragraphs.append(text)

        if len(paragraphs) >= 3:
            return paragraphs

    return []


def scrape_article(url: str, timeout: int = 15) -> ScrapedArticle:
    """Fetch and parse an article URL. Raises on HTTP errors or no content."""
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove script/style/noscript noise
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    domain_key = _domain_key(url)
    title = _extract_title(soup)
    paragraphs = _extract_paragraphs(soup, domain_key)

    if not paragraphs:
        raise ValueError("Could not extract article content from this URL")

    text = "\n\n".join(paragraphs)
    word_count = len(text.split())

    return ScrapedArticle(
        title=title,
        text=text,
        paragraphs=paragraphs,
        url=url,
        domain=urlparse(url).netloc,
        word_count=word_count,
    )
