from __future__ import annotations

import json
from pathlib import Path

import requests

from product_scraper import (
    API_URL,
    EXTRACTED_DIR,
    REQUEST_TIMEOUT,
    build_headers,
    get_auth_token,
    load_config,
)


CATEGORY = {
    "name": "Green Tea sample",
    "slug": "green-tea",
    "url": "https://www.apollopharmacy.in/shop-by-category/green-tea",
}
OUTPUT_PATH = EXTRACTED_DIR / "green_tea_sample_response.json"
QUERY = """query getAplCategoryProducts($categoryId: Int, $axdcCode: String, $composition: String, $skus: String, $category_url: String, $page_id: Int, $filters: JSON, $sort_by: String, $lat: Float, $lng: Float, $size: Int, $pincode: String) {
  getAplCategoryProducts(
    categoryId: $categoryId
    axdcCode: $axdcCode
    composition: $composition
    skus: $skus
    category_url: $category_url
    page_id: $page_id
    filters: $filters
    sort_by: $sort_by
    lat: $lat
    lng: $lng
    size: $size
    pincode: $pincode
  ) {
    count
    products
    category_id
    __typename
  }
}
"""


def main() -> int:
    config = load_config()
    token = get_auth_token(config)
    payload = {
        "operationName": "getAplCategoryProducts",
        "variables": {
            "category_url": "green-tea",
            "page_id": 1,
            "lat": 19.223647947149935,
            "lng": 73.10226382004917,
            "size": 24,
            "pincode": "421201",
        },
        "query": QUERY,
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = build_headers(token, CATEGORY)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        response = session.post(
            API_URL,
            headers=headers,
            data=body,
            timeout=REQUEST_TIMEOUT,
        )

    OUTPUT_PATH.write_bytes(response.content)
    print(f"HTTP status: {response.status_code}")
    print(f"Saved response to: {OUTPUT_PATH}")
    if not response.ok:
        response.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
