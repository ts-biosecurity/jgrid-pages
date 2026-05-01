"""
Fetch news from WHO Myanmar (https://www.who.int/myanmar) and the SEARO regional
news that is surfaced on that page, normalize them to the same JSON schema used
by ``fetch_gnlm.py`` / ``fetch.py`` and write ``myanmar_who.json``.

DEPLOYMENT NOTE:
    This file is staged in the public ``jgrid-pages`` repo for review only.
    The scheduled execution lives in the private ``jgrid-fetch`` repo at:
        jgrid-fetch/myanmar/fetch_who_myanmar.py
    Add this script to ``.github/workflows/myanmar.yml`` after fetch_gnlm.py.

Output schema (matches the article schema consumed by index.html):
    {
        "generated_at": ISO8601,
        "date_range": { "start": ISO8601, "end": ISO8601 },
        "total_articles": int,
        "articles": [
            {
                "articleId": "who_<hash>",
                "headline": str,            # English title
                "headlineJa": str,          # Japanese (deep_translator)
                "headlineTranslated": "",
                "summary": str,             # English description
                "summaryJa": str,
                "publishedTimestamp": ISO8601,
                "sourceUrl": str,           # canonical detail page URL
                "originalLanguage": "ENGLISH",
                "diseases": [str, ...],     # matched disease keywords
                "locations": [],
                "states": ["Myanmar (region not identified)"],  # WHO doesn't tag at state level
                "dataSource": "WHO Myanmar",
                "sourceName": "WHO Myanmar" | "WHO South-East Asia",
                "category": str            # e.g. "News release", "Statement", "Feature story"
            }, ...
        ]
    }
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

try:
    from deep_translator import GoogleTranslator
except ImportError:  # translation is optional; keep ETL working without it
    GoogleTranslator = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fetch_who_myanmar")

# Source pages to scrape. Each entry is (url, source_name).
SOURCE_PAGES: list[tuple[str, str]] = [
    ("https://www.who.int/myanmar", "WHO Myanmar"),
    ("https://www.who.int/myanmar/news", "WHO Myanmar"),
    ("https://www.who.int/myanmar/news/feature-stories", "WHO Myanmar"),
]

# Disease / health-relevance keywords. Loose match (case-insensitive substring on
# headline + description). Keep aligned with fetch_gnlm.py vocabulary.
DISEASE_KEYWORDS: dict[str, list[str]] = {
    "Dengue":          ["dengue"],
    "Malaria":         ["malaria"],
    "Influenza":       ["influenza", "h5n1", "h7n9", "h1n1", "avian flu", "bird flu"],
    "Tuberculosis":    ["tuberculosis", " tb "],
    "Measles":         ["measles"],
    "Cholera":         ["cholera"],
    "Hepatitis":       ["hepatitis"],
    "Typhoid":         ["typhoid"],
    "Leptospirosis":   ["leptospirosis"],
    "Japanese Encephalitis": ["japanese encephalitis"],
    "Rabies":          ["rabies"],
    "Diphtheria":      ["diphtheria"],
    "Pertussis":       ["pertussis"],
    "HIV":             [" hiv "],
    "Leprosy":         ["leprosy"],
    "Chikungunya":     ["chikungunya"],
    "Zika":            ["zika"],
    "Mpox":            ["mpox", "monkeypox"],
    "Ebola":           ["ebola"],
    "Meningitis":      ["meningitis"],
    "Plague":          ["plague"],
    "Scrub Typhus":    ["scrub typhus"],
    "COVID-19":        ["covid"],
    "ARI":             ["acute respiratory infection", "respiratory infection"],
    "Acute Diarrhoea": ["acute diarrhoea", "acute diarrhea", "watery diarrhoea"],
    "Snakebite":       ["snakebite", "snake bite"],
}

# Broader health keywords that keep an article in the dataset even without a
# specific disease tag (the article is still useful context for an ID dashboard).
HEALTH_KEYWORDS: list[str] = [
    "outbreak", "epidemic", "vaccin", "immuniz", "immunis",
    "surveillance", "communicable disease", "public health emergency",
    "disease control", "infection prevention",
]

# Keep articles within this many days. WHO Myanmar publishes infrequently so we
# use a longer window than Google News (72h).
LOOKBACK_DAYS = int(os.environ.get("WHO_MYANMAR_LOOKBACK_DAYS", "180"))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

DATE_FORMATS = ("%d %B %Y", "%d %b %Y")


def _parse_date(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _absolutize(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://www.who.int" + href
    return href


def _make_id(url: str) -> str:
    return "who_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _classify_diseases(text: str) -> list[str]:
    t = text.lower()
    matched: list[str] = []
    for disease, keywords in DISEASE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(k.strip())}\b", t) for k in keywords):
            matched.append(disease)
    return matched


def _is_health_related(text: str) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(k)}", t) for k in HEALTH_KEYWORDS)


def _fetch_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None


def _extract_items(html: str, page_url: str, source_name: str) -> Iterable[dict]:
    """Parse list-view--item blocks present on /myanmar and /myanmar/news pages.

    Each block looks like::

        <div class="list-view--item ...">
          <a href="..." class="link-container" aria-label="Title">
            <div class="info">
              <div class="date"><span class="timestamp">24 April 2026</span>
                <div class="sf-tags-list-item">News release</div>
              </div>
              <p class="heading text-underline">Title</p>
            </div>
          </a>
        </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    for block in soup.select("div.list-view--item"):
        link = block.select_one("a.link-container")
        if not link or not link.get("href"):
            continue
        href = _absolutize(link["href"])

        # Title: prefer aria-label, fall back to .heading text
        title = (link.get("aria-label") or "").strip()
        if not title:
            heading = block.select_one(".heading")
            title = heading.get_text(strip=True) if heading else ""
        if not title:
            continue

        # Date from <span class="timestamp">
        ts_el = block.select_one("span.timestamp")
        ts_raw = ts_el.get_text(strip=True) if ts_el else ""
        published = _parse_date(ts_raw)
        if not published or published < cutoff:
            continue

        category_el = block.select_one(".sf-tags-list-item")
        category = category_el.get_text(strip=True) if category_el else ""

        # Disambiguate sub-source: SEAR regional content vs Myanmar-country
        if "/southeastasia/" in href:
            sub_source = "WHO South-East Asia"
        else:
            sub_source = source_name

        yield {
            "url": href,
            "title": title,
            "published": published,
            "category": category,
            "sourceName": sub_source,
            "fetchedFrom": page_url,
        }


def _fetch_summary(detail_url: str) -> str:
    """Best-effort extraction of the lead paragraph from a WHO detail page."""
    html = _fetch_page(detail_url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        "div.sf-detail-body-wrapper p",
        "article p",
        "div.entry-content p",
    ):
        p = soup.select_one(selector)
        if p:
            text = p.get_text(strip=True)
            if len(text) > 40:
                return text[:600]
    return ""


def _translate(text: str) -> str:
    if not text or GoogleTranslator is None:
        return ""
    try:
        return GoogleTranslator(source="en", target="ja").translate(text) or ""
    except Exception as exc:
        log.warning("Translation failed: %s", exc)
        return ""


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "myanmar_who.json"

    seen: set[str] = set()
    items: list[dict] = []

    for page_url, source_name in SOURCE_PAGES:
        log.info("Fetching %s", page_url)
        html = _fetch_page(page_url)
        if not html:
            continue
        for it in _extract_items(html, page_url, source_name):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            items.append(it)

    log.info("Collected %d unique items before filtering", len(items))

    articles: list[dict] = []
    for it in items:
        # Lazily fetch summary only if we need it for keyword matching
        summary = _fetch_summary(it["url"]) if it["title"] else ""
        full_text = f"{it['title']} {summary}"
        diseases = _classify_diseases(full_text)
        if not diseases and not _is_health_related(full_text):
            continue

        published_iso = it["published"].isoformat()
        article = {
            "articleId": _make_id(it["url"]),
            "headline": it["title"],
            "headlineTranslated": "",
            "headlineJa": _translate(it["title"]),
            "summary": summary,
            "summaryOriginal": summary,
            "summaryJa": _translate(summary) if summary else "",
            "publishedTimestamp": published_iso,
            "sourceUrl": it["url"],
            "originalLanguage": "ENGLISH",
            "diseases": diseases,
            "locations": [],
            "states": ["Myanmar (region not identified)"],
            "dataSource": "WHO Myanmar",
            "sourceName": it["sourceName"],
            "category": it["category"],
        }
        articles.append(article)

    articles.sort(key=lambda a: a["publishedTimestamp"], reverse=True)
    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(),
        "date_range": {
            "start": (now - timedelta(days=LOOKBACK_DAYS)).isoformat(),
            "end": now.isoformat(),
        },
        "total_articles": len(articles),
        "articles": articles,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote %d articles to %s", len(articles), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
