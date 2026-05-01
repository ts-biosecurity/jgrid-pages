"""
Fetch infectious-disease related news from Eleven Media (https://elevenmyanmar.com),
normalize them to the same JSON schema used by ``fetch.py`` / ``fetch_gnlm.py`` /
``fetch_who_myanmar.py`` and write ``myanmar_eleven.json``.

DEPLOYMENT NOTE:
    This file is staged in the public ``jgrid-pages`` repo for review only.
    The scheduled execution lives in the private ``jgrid-fetch`` repo at:
        jgrid-fetch/myanmar/fetch_eleven_myanmar.py
    Add this script to ``.github/workflows/myanmar.yml`` after fetch_who_myanmar.py.

Approach:
- Eleven Myanmar's site-wide RSS is stale (last items from 2022). We instead use
  the Drupal-style search at ``/search/node/<keyword>`` per disease keyword. The
  search returns results roughly in publication-date-descending order, with
  ``<div class="search-title"><a href=...>`` blocks. Pagination is ``?page=N`` but
  we only fetch the first page (10 results) per keyword.
- Each article detail page exposes the publish timestamp via:
    <span class="date-display-single" property="dc:date"
          datatype="xsd:dateTime" content="2026-01-30T08:45:15+06:30">...</span>
- Lead paragraph is extracted from the body field for summary/classification.
- Articles are kept only if they (a) fall within ELEVEN_LOOKBACK_DAYS and
  (b) match a disease keyword on title + summary text (the search itself is
  noisy: "outbreak" matches fire-drill stories etc., so we re-classify).

Output schema mirrors fetch_who_myanmar.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fetch_eleven_myanmar")

BASE = "https://elevenmyanmar.com"

# Disease keywords used for both the Drupal search query AND the post-fetch
# classifier. Keep aligned with fetch_gnlm.py / fetch_who_myanmar.py vocabulary.
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
    "Nipah":           ["nipah"],
    "COVID-19":        ["covid"],
    "ARI":             ["acute respiratory infection", "respiratory infection"],
    "Acute Diarrhoea": ["acute diarrhoea", "acute diarrhea", "watery diarrhoea"],
    "Snakebite":       ["snakebite", "snake bite"],
}

# Search queries to issue against /search/node/<term>. Includes both individual
# disease names and a few broader public-health terms.
SEARCH_TERMS: list[str] = [
    "dengue", "malaria", "influenza", "avian flu", "bird flu", "tuberculosis",
    "measles", "cholera", "hepatitis", "typhoid", "leptospirosis",
    "japanese encephalitis", "rabies", "diphtheria", "chikungunya", "zika",
    "mpox", "monkeypox", "ebola", "meningitis", "scrub typhus", "nipah",
    "covid", "h5n1", "outbreak", "epidemic", "vaccination", "vaccine",
    "infectious", "respiratory infection", "acute diarrhoea",
]

# Broader health words that keep an article in the dataset even without a
# specific disease tag (kept rare to limit noise from this aggregator).
HEALTH_KEYWORDS: list[str] = [
    "outbreak", "epidemic", "vaccin", "immuniz", "immunis",
    "surveillance", "communicable disease", "public health emergency",
]

LOOKBACK_DAYS = int(os.environ.get("ELEVEN_LOOKBACK_DAYS", "180"))
RESULTS_PER_KEYWORD = int(os.environ.get("ELEVEN_RESULTS_PER_KEYWORD", "10"))
REQUEST_DELAY_SEC = float(os.environ.get("ELEVEN_REQUEST_DELAY", "0.4"))
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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


def _make_id(url: str) -> str:
    return "eleven_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None
    finally:
        if REQUEST_DELAY_SEC > 0:
            time.sleep(REQUEST_DELAY_SEC)


def _search_urls(term: str) -> list[str]:
    """Return article URLs from the first page of /search/node/<term>."""
    url = f"{BASE}/search/node/{quote(term)}"
    html = _fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen: list[str] = []
    seen_set: set[str] = set()
    for sr in soup.select("div.search-result"):
        title = sr.select_one("div.search-title a")
        if not title or not title.get("href"):
            continue
        href = title["href"].strip()
        if not href.startswith(BASE + "/news/"):
            continue
        if href in seen_set:
            continue
        seen_set.add(href)
        seen.append(href)
        if len(seen) >= RESULTS_PER_KEYWORD:
            break
    log.info("search %-30s -> %d results", term, len(seen))
    return seen


def _parse_detail(url: str) -> dict | None:
    """Return {title, summary, published} for an article URL, or None on failure."""
    html = _fetch(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Title — prefer the detail-page title block, fall back to og:title.
    # Note: og:title on Eleven Myanmar sometimes returns the site name
    # ("Eleven Media Group Co., Ltd") instead of the article title, so the
    # in-page selectors below are tried first.
    title = ""
    for sel in ("div.news-detail-title", "h1.page-title-news", "h1.page-title", "h1"):
        el = soup.select_one(sel)
        if el:
            title = el.get_text(" ", strip=True)
            if title and "Eleven Media Group" not in title:
                break
            title = ""
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            cand = og["content"].strip()
            if cand and "Eleven Media Group" not in cand:
                title = cand
    if not title:
        return None

    # Publish timestamp from <span class="date-display-single" content="ISO">
    ts_el = soup.select_one("div.news-detail-date-author-info-date span.date-display-single")
    if ts_el is None:
        ts_el = soup.select_one("span.date-display-single")
    iso = ts_el.get("content") if ts_el and ts_el.has_attr("content") else ""
    published = None
    if iso:
        try:
            published = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            published = None
    if not published:
        return None
    published = published.astimezone(timezone.utc)

    # Lead paragraph from the body field
    summary = ""
    for sel in (
        "div.field-name-body div.field-item p",
        "div.news-detail-content p",
        "article p",
    ):
        for p in soup.select(sel):
            text = p.get_text(" ", strip=True)
            if len(text) > 40:
                summary = text[:600]
                break
        if summary:
            break

    return {"title": title, "summary": summary, "published": published, "url": url}


def _translate(text: str) -> str:
    if not text or GoogleTranslator is None:
        return ""
    try:
        return GoogleTranslator(source="en", target="ja").translate(text) or ""
    except Exception as exc:
        log.warning("Translation failed: %s", exc)
        return ""


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "myanmar_eleven.json"

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    candidate_urls: list[str] = []
    seen_urls: set[str] = set()
    for term in SEARCH_TERMS:
        for u in _search_urls(term):
            if u not in seen_urls:
                seen_urls.add(u)
                candidate_urls.append(u)

    log.info("Total unique candidate URLs: %d", len(candidate_urls))

    articles: list[dict] = []
    for url in candidate_urls:
        item = _parse_detail(url)
        if not item:
            continue
        if item["published"] < cutoff:
            continue
        full_text = f"{item['title']} {item['summary']}"
        diseases = _classify_diseases(full_text)
        if not diseases and not _is_health_related(full_text):
            continue

        articles.append({
            "articleId": _make_id(url),
            "headline": item["title"],
            "headlineTranslated": "",
            "headlineJa": _translate(item["title"]),
            "summary": item["summary"],
            "summaryOriginal": item["summary"],
            "summaryJa": _translate(item["summary"]) if item["summary"] else "",
            "publishedTimestamp": item["published"].isoformat(),
            "sourceUrl": url,
            "originalLanguage": "ENGLISH",
            "diseases": diseases,
            "locations": [],
            "states": ["Myanmar (region not identified)"],
            "dataSource": "Eleven Myanmar",
            "sourceName": "Eleven Myanmar",
            "category": "News",
        })

    articles.sort(key=lambda a: a["publishedTimestamp"], reverse=True)

    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(),
        "date_range": {
            "start": cutoff.isoformat(),
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
