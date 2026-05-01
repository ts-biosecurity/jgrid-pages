"""
Fetch infectious-disease related news from Myanmar Now (https://myanmar-now.org/en/),
normalize them to the same JSON schema used by the other Myanmar fetchers
(``fetch.py`` / ``fetch_gnlm.py`` / ``fetch_eleven_myanmar.py`` / etc.) and write
``myanmar_now.json``.

DEPLOYMENT NOTE:
    This file is staged in the public ``jgrid-pages`` repo for review only.
    The scheduled execution lives in the private ``jgrid-fetch`` repo at:
        jgrid-fetch/myanmar/fetch_myanmar_now.py
    Add this script to ``.github/workflows/myanmar.yml`` after fetch_eleven_myanmar.py.

Approach:
- Myanmar Now is a WordPress site that exposes the standard WP REST API at
  ``/en/wp-json/wp/v2/posts``. The site-wide RSS at ``/en/feed/`` only returns
  the 10 most recent items (mostly political), so we use per-keyword REST search
  instead: ``?search=<term>&per_page=20&orderby=date&order=desc``.
- The REST response includes ``id``, ``date``, ``link``, ``title.rendered``,
  ``excerpt.rendered`` (HTML), and ``content.rendered`` — no detail-page fetch
  required.
- Articles are kept only if (a) within MYANMAR_NOW_LOOKBACK_DAYS and (b) match
  a disease keyword on the combined title + excerpt + content text. Search by
  itself is noisy (e.g., "dengue" matches articles where the word only appears
  in body context), so we always re-classify.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fetch_myanmar_now")

REST_BASE = "https://myanmar-now.org/en/wp-json/wp/v2/posts"

# Disease keywords (same vocabulary as fetch_eleven_myanmar.py).
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

SEARCH_TERMS: list[str] = [
    "dengue", "malaria", "influenza", "avian flu", "bird flu", "tuberculosis",
    "measles", "cholera", "hepatitis", "typhoid", "leptospirosis",
    "japanese encephalitis", "rabies", "diphtheria", "chikungunya", "zika",
    "mpox", "monkeypox", "ebola", "meningitis", "scrub typhus", "nipah",
    "covid", "h5n1", "outbreak", "epidemic", "vaccination", "vaccine",
    "infectious", "respiratory infection", "acute diarrhoea",
]

HEALTH_KEYWORDS: list[str] = [
    "outbreak", "epidemic", "vaccin", "immuniz", "immunis",
    "surveillance", "communicable disease", "public health emergency",
]

LOOKBACK_DAYS = int(os.environ.get("MYANMAR_NOW_LOOKBACK_DAYS", "180"))
RESULTS_PER_KEYWORD = int(os.environ.get("MYANMAR_NOW_RESULTS_PER_KEYWORD", "20"))
REQUEST_DELAY_SEC = float(os.environ.get("MYANMAR_NOW_REQUEST_DELAY", "0.4"))
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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


def _make_id(post_id: int, link: str) -> str:
    raw = f"{post_id}|{link}"
    return "mnow_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _search_posts(term: str) -> list[dict[str, Any]]:
    """Hit WP REST API search and return the parsed array (or [] on failure)."""
    url = f"{REST_BASE}?search={quote(term)}&per_page={RESULTS_PER_KEYWORD}&orderby=date&order=desc"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("Search failed for %s: %s", term, exc)
        return []
    finally:
        if REQUEST_DELAY_SEC > 0:
            time.sleep(REQUEST_DELAY_SEC)
    if not isinstance(data, list):
        return []
    log.info("search %-30s -> %d results", term, len(data))
    return data


def _translate(text: str) -> str:
    if not text or GoogleTranslator is None:
        return ""
    try:
        return GoogleTranslator(source="en", target="ja").translate(text) or ""
    except Exception as exc:
        log.warning("Translation failed: %s", exc)
        return ""


def _post_to_article(post: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a WP REST post object to an article dict, or None if invalid."""
    link = post.get("link") or ""
    if not link:
        return None
    post_id = int(post.get("id") or 0)
    title = _strip_html((post.get("title") or {}).get("rendered", ""))
    if not title:
        return None
    excerpt = _strip_html((post.get("excerpt") or {}).get("rendered", ""))
    content = _strip_html((post.get("content") or {}).get("rendered", ""))
    summary = excerpt or content[:600]

    date_raw = post.get("date_gmt") or post.get("date") or ""
    if not date_raw:
        return None
    if not date_raw.endswith("Z") and "+" not in date_raw:
        # WP returns date_gmt without timezone suffix; treat as UTC.
        date_raw = date_raw + "+00:00"
    try:
        published = datetime.fromisoformat(date_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None

    return {
        "id": post_id,
        "link": link,
        "title": title,
        "summary": summary[:600],
        "full_text": f"{title} {excerpt} {content[:1500]}",
        "published": published,
    }


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "myanmar_now.json"

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    seen_links: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for term in SEARCH_TERMS:
        for post in _search_posts(term):
            item = _post_to_article(post)
            if not item:
                continue
            if item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            candidates.append(item)

    log.info("Total unique candidates: %d", len(candidates))

    articles: list[dict[str, Any]] = []
    for item in candidates:
        if item["published"] < cutoff:
            continue
        diseases = _classify_diseases(item["full_text"])
        if not diseases and not _is_health_related(item["full_text"]):
            continue

        articles.append({
            "articleId": _make_id(item["id"], item["link"]),
            "headline": item["title"],
            "headlineTranslated": "",
            "headlineJa": _translate(item["title"]),
            "summary": item["summary"],
            "summaryOriginal": item["summary"],
            "summaryJa": _translate(item["summary"]) if item["summary"] else "",
            "publishedTimestamp": item["published"].isoformat(),
            "sourceUrl": item["link"],
            "originalLanguage": "ENGLISH",
            "diseases": diseases,
            "locations": [],
            "states": ["Myanmar (region not identified)"],
            "dataSource": "Myanmar Now",
            "sourceName": "Myanmar Now",
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
