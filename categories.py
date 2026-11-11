from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


BASE_DIR = Path(__file__).resolve().parent
COMMON_DIR = BASE_DIR.parent / "scraper-common"
sys.path.insert(0, str(COMMON_DIR))
os.environ.setdefault("SCRAPER_NETWORK_GUARD", "1")

import shared_network_guard  # noqa: E402,F401


SITEMAP_URL = "https://www.apollopharmacy.in/sitemap/sitemap-pharmacy-category-a-1.xml"
OUTPUT_DIR = BASE_DIR / "extracted_content"
OUTPUT_FILE = OUTPUT_DIR / "categories.json"
REQUEST_TIMEOUT = 30
SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def extract_categories(xml_content: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_content)
    categories: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in root.findall(f"{SITEMAP_NAMESPACE}url"):
        location = (item.findtext(f"{SITEMAP_NAMESPACE}loc") or "").strip()
        if not location or location in seen_urls:
            continue

        parsed = urlparse(location)
        if parsed.netloc.lower() not in {"www.apollopharmacy.in", "apollopharmacy.in"}:
            continue

        slug = parsed.path.rstrip("/").split("/")[-1]
        if not slug:
            continue

        category = {
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "url": location,
        }
        last_modified = (item.findtext(f"{SITEMAP_NAMESPACE}lastmod") or "").strip()
        if last_modified:
            category["lastmod"] = last_modified

        categories.append(category)
        seen_urls.add(location)

    return categories


def save_categories(categories: list[dict[str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SITEMAP_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "category_count": len(categories),
        "categories": categories,
    }
    temporary_file = OUTPUT_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_file.replace(OUTPUT_FILE)


def main() -> int:
    response = requests.get(
        SITEMAP_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ApolloCategoryScraper/1.0)"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    categories = extract_categories(response.content)
    if not categories:
        raise RuntimeError("The sitemap response did not contain any Apollo Pharmacy category URLs.")

    save_categories(categories)
    print(f"Extracted {len(categories)} categories.")
    print(f"Saved categories to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
