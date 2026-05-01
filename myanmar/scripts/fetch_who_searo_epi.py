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
                "descriptionJa": str,
                # Top-3 issues only: Myanmar-specific excerpts pulled from the PDF
                "myanmarExcerpts": [
                    {
                        "section": "Influenza",          # nearest top-level section
                        "page": 8,                       # page number in the PDF
                        "text": "...",                   # English excerpt
                        "textJa": "..."                  # Japanese translation
                    }, ...
                ]
            }, ...
        ]
    }

The bulletin is biweekly so we keep the latest 24 issues by default (~1 year).
Myanmar excerpts are extracted from the latest ``EXCERPT_TOP_N`` (default 3)
PDFs only, to bound run-time and download volume.
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

try:
    from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore[import]
except ImportError:
    pdf_extract_text = None  # type: ignore[assignment]

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
EXCERPT_TOP_N = int(os.environ.get("WHO_SEARO_EPI_EXCERPT_TOP_N", "3"))

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


def _fetch_pdf(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT * 2)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        log.warning("Failed to download PDF %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Myanmar excerpt extraction from bulletin PDFs
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    r"^(Key events and updates|Influenza|COVID-19|mpox|Dengue|Measles|Cholera|"
    r"Diphtheria|Chikungunya|Zika|Avian Influenza|Tuberculosis|Malaria|"
    r"Japanese Encephalitis|Leptospirosis|Acute Respiratory|Acute Diarrhea)\b",
    re.IGNORECASE,
)
_CITATION_RE = re.compile(r"(?<=[A-Za-z])(\d{1,2})(?=[\s,\.\)\]])")
_BULLET_PREFIX_RE = re.compile(r"^[o•·∙•]\s+")
_REF_LINE_RE = re.compile(
    r"^\d+\s+(Ministry|World Health|Available|Republic|Government|MoH|WHO)",
    re.IGNORECASE,
)
_UNIT_SPLIT_RE = re.compile(r"(?m)(?=^\s*(?:•|Notes:|Figure \d+\.))")


def _normalize_unit(s: str) -> str:
    s = re.sub(r"-\n", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _CITATION_RE.sub("", s)
    s = _BULLET_PREFIX_RE.sub("", s)
    return s


def _detect_section(page_text: str) -> str | None:
    for line in page_text.split("\n")[:8]:
        s = line.strip()
        if not s or len(s) >= 80:
            continue
        m = _SECTION_RE.match(s)
        if m:
            return m.group(1)
    return None


def extract_myanmar_excerpts(pdf_bytes: bytes) -> list[dict]:
    """Return a list of Myanmar-specific excerpts from a SEARO Epi PDF."""
    if pdf_extract_text is None:
        log.warning("pdfminer.six is not installed; skipping excerpt extraction")
        return []
    from io import BytesIO
    try:
        text = pdf_extract_text(BytesIO(pdf_bytes))
    except Exception as exc:
        log.warning("PDF text extraction failed: %s", exc)
        return []

    pages = text.split("\f")
    current_section: str | None = None
    out: list[dict] = []
    seen: set[str] = set()

    for page_num, page_text in enumerate(pages, start=1):
        detected = _detect_section(page_text)
        if detected:
            current_section = detected

        flat = re.sub(r"-\n", "", page_text)
        flat = re.sub(r"\n+", "\n", flat)
        for unit in _UNIT_SPLIT_RE.split(flat):
            u_clean = _normalize_unit(unit)
            if "myanmar" not in u_clean.lower():
                continue
            if _REF_LINE_RE.match(u_clean):
                continue

            sentences = re.split(r"(?<=[.!?])\s+", u_clean)
            kept: list[str] = []
            for sent in sentences:
                if "myanmar" not in sent.lower():
                    continue
                if re.match(r"^\d+\s+\w+", sent) and "http" in sent.lower():
                    continue
                sl = sent.lower().strip()
                if sl.startswith("available from") or sl.startswith("https://") or sl.startswith("http://"):
                    continue
                kept.append(_BULLET_PREFIX_RE.sub("", sent.strip()))
            if not kept:
                continue

            text_out = " ".join(kept)
            text_out = re.sub(r"\s+", " ", text_out).strip(" •.,;")
            if len(text_out) < 15:
                continue
            if not text_out.endswith((".", "!", "?")):
                text_out += "."

            key = text_out[:80].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "section": current_section or "Unknown",
                "page": page_num,
                "text": text_out,
            })
    return out


def _translate_excerpts(excerpts: list[dict]) -> list[dict]:
    if not excerpts or GoogleTranslator is None:
        return excerpts
    translator = GoogleTranslator(source="en", target="ja")
    for ex in excerpts:
        try:
            ex["textJa"] = translator.translate(ex["text"]) or ""
        except Exception as exc:
            log.warning("Excerpt translation failed: %s", exc)
            ex["textJa"] = ""
    return excerpts


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

    # Extract Myanmar-specific excerpts from the latest EXCERPT_TOP_N PDFs.
    for b in items[:EXCERPT_TOP_N]:
        pdf_url = b.get("pdfUrl")
        if not pdf_url:
            b["myanmarExcerpts"] = []
            continue
        log.info("Downloading PDF for Myanmar excerpts: %s", pdf_url)
        pdf_bytes = _fetch_pdf(pdf_url)
        if not pdf_bytes:
            b["myanmarExcerpts"] = []
            continue
        excerpts = extract_myanmar_excerpts(pdf_bytes)
        excerpts = _translate_excerpts(excerpts)
        b["myanmarExcerpts"] = excerpts
        log.info("  edition %s: %d Myanmar excerpts", b.get("edition"), len(excerpts))

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
