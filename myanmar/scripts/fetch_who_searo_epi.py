"""
Fetch the latest issues of the WHO SEARO Epidemiological Bulletin from
https://www.who.int/southeastasia/outbreaks-and-emergencies/surveillance-and-alert/sear-epi-bulletins
and write ``who_searo_epi.json`` for the Myanmar dashboard.

DEPLOYMENT NOTE:
    Staged in the public ``jgrid-pages`` repo for review only. Move to
    ``jgrid-fetch/myanmar/fetch_who_searo_epi.py`` and add a step in
    ``.github/workflows/myanmar.yml`` after fetch_who_myanmar.py.

Output schema (consumed by index.html ``renderSearoEpi``)::

    {
        "generated_at": ISO8601,
        "source_url": "https://www.who.int/southeastasia/.../sear-epi-bulletins",
        "total_bulletins": int,
        "bulletins": [
            {
                "id": "searoepi_<hash>",
                "title": str,           # e.g. "08th edition, Epidemiological Bulletin..."
                "titleJa": str,         # optional Japanese
                "date": ISO8601,        # publication date
                "edition": str | None,  # e.g. "08", or None
                "year": int | None,
                "pageUrl": str,         # /southeastasia/publications/i/item/<id>
                "pdfUrl": str | None,   # iris.who.int/.../content
                "description": str,     # marketing blurb
                "descriptionJa": str
            }, ...
        ]
    }

The bulletin is biweekly so we keep the latest 24 issues by default (~1 year).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fetch_who_searo_epi")

SOURCE_URL = (
    "https://www.who.int/southeastasia/outbreaks-and-emergencies/"
    "surveillance-and-alert/sear-epi-bulletins"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
MAX_BULLETINS = int(os.environ.get("WHO_SEARO_EPI_MAX", "24"))

DATE_FORMATS = ("%d %B %Y", "%d %b %Y")


def _parse_date(raw: str) -> datetime | None:
    s = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _absolutize(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://www.who.int" + href
    return href


def _make_id(url: str) -> str:
    return "searoepi_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


_EDITION_RE = re.compile(r"^(\d+)(?:st|nd|rd|th)?\s+edition", re.IGNORECASE)


def _parse_edition(title: str) -> str | None:
    m = _EDITION_RE.search(title)
    if not m:
        return None
    return m.group(1).zfill(2)


def _translate(text: str) -> str:
    if not text or GoogleTranslator is None:
        return ""
    try:
        return GoogleTranslator(source="en", target="ja").translate(text) or ""
    except Exception as exc:
        log.warning("Translation failed: %s", exc)
        return ""


def _fetch_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None


def _extract_bulletins(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for item in soup.select("div.sf-publications-item"):
        title_el = item.select_one(".sf-publications-item__title")
        date_el = item.select_one(".sf-publications-item__date span")
        page_link = item.select_one(".sf-publications-item__url a, .sf-publications-item__header a")
        pdf_link = item.select_one("a.download-url")
        desc_el = item.select_one(".sf-publications-item__description")

        if not title_el or not page_link:
            continue
        title = title_el.get_text(strip=True)
        page_url = _absolutize(page_link.get("href"))
        if not page_url:
            continue

        date_raw = date_el.get_text(strip=True) if date_el else ""
        published = _parse_date(date_raw)
        pdf_url = _absolutize(pdf_link.get("href")) if pdf_link else None
        description = desc_el.get_text(strip=True) if desc_el else ""

        out.append({
            "id": _make_id(page_url),
            "title": title,
            "date": published.isoformat() if published else None,
            "edition": _parse_edition(title),
            "year": published.year if published else None,
            "pageUrl": page_url,
            "pdfUrl": pdf_url,
            "description": description,
        })
    return out


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "who_searo_epi.json"

    log.info("Fetching %s", SOURCE_URL)
    html = _fetch_page(SOURCE_URL)
    if not html:
        log.error("Could not fetch source page; aborting")
        return 1

    items = _extract_bulletins(html)
    log.info("Parsed %d bulletins", len(items))

    items.sort(key=lambda b: b.get("date") or "", reverse=True)
    items = items[:MAX_BULLETINS]

    # Translate the most recent few only (keep run-time bounded).
    for b in items[:6]:
        b["titleJa"] = _translate(b["title"])
        if b.get("description"):
            b["descriptionJa"] = _translate(b["description"])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "total_bulletins": len(items),
        "bulletins": items,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote %d bulletins to %s", len(items), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
