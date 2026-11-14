from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests


PROJECT_DIR = Path(__file__).resolve().parent
COMMON_DIR = PROJECT_DIR.parent / "scraper-common"
EXTRACTED_DIR = PROJECT_DIR / "extracted_content"
CATEGORIES_PATH = EXTRACTED_DIR / "categories.json"
OUTPUT_PATH = EXTRACTED_DIR / "apollopharmacy_products.csv"
CONFIG_PATH = PROJECT_DIR / "config.json"
API_URL = "https://api.apollo247.com/"
AUTH_URL = "https://apigateway.apollo247.in/auth-service/fetchAuthToken"
PRODUCT_URL_BASE = "https://www.apollopharmacy.in/otc/"
PAGE_SIZE = 24
DISCOUNT_THRESHOLD = 50.0
REQUEST_TIMEOUT = 40
REQUEST_GAP_SECONDS = (1.2, 2.0)
MAX_REQUEST_ATTEMPTS = 5
HTTP_429_PAUSES = (10.0, 20.0, 20.0, 20.0, 20.0)

CSV_HEADERS = [
    "Product ID",
    "SKU",
    "Product Name",
    "Brand",
    "MRP",
    "Price",
    "Discount %",
    "Availability",
    "Product URL",
    "Super Category",
    "Category",
    "Subcategory",
    "Discount Valid till",
    "Image URLs",
]

sys.path.insert(0, str(COMMON_DIR))
os.environ.setdefault("SCRAPER_NETWORK_GUARD", "1")

import shared_network_guard  # noqa: E402,F401
from shared_config import shared_location  # noqa: E402
from shared_network_guard import (  # noqa: E402
    ConsecutiveNetworkFailureLimit,
    reset_failure_counter,
)


class CategoryRequestAborted(Exception):
    """Raised when the shared guard reaches its consecutive-failure limit."""


GRAPHQL_QUERY = """query getAplCategoryProducts($categoryId: Int, $axdcCode: String, $composition: String, $skus: String, $category_url: String, $page_id: Int, $filters: JSON, $sort_by: String, $lat: Float, $lng: Float, $size: Int, $pincode: String) {
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
}"""


def load_config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def load_categories() -> list[dict[str, str]]:
    payload = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    raw_categories = payload.get("categories", [])
    return [item for item in raw_categories if isinstance(item, dict) and item.get("slug")]


def get_auth_token(config: dict[str, Any]) -> str:
    token = os.environ.get("APOLLO_AUTH_TOKEN") or config.get("authorization") or config.get("auth_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(
            "Apollo authorization is missing. Set APOLLO_AUTH_TOKEN or add 'authorization' to config.json."
        )
    return token.strip()


def get_location(config: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("SCRAPER_LOCATION_OVERRIDE") == "1":
        return shared_location(config)

    project_location = config.get("location")
    if isinstance(project_location, dict) and all(
        project_location.get(key) not in (None, "") for key in ("lat", "lon", "pincode")
    ):
        return {
            "lat": project_location["lat"],
            "lon": project_location["lon"],
            "lng": project_location["lon"],
            "pincode": project_location["pincode"],
        }
    return shared_location()


def build_headers(token: str, category: dict[str, str]) -> dict[str, str]:
    trace_id = uuid.uuid4().hex
    span_id = secrets.token_hex(8)
    return {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "DNT": "1",
        "Origin": "https://www.apollopharmacy.in",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": category.get("url") or f"https://www.apollopharmacy.in/shop-by-category/{category['slug']}",
        "Sec-CH-UA": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "X-Correlation-Id": "null",
        "X-Device-Id": "8a7f3eb3-4717-4124-bc9a-e34a5d5cd9f8",
        "Traceparent": f"00-{trace_id}-{span_id}-00",
    }


def build_auth_headers(bootstrap_token: str, category: dict[str, str]) -> dict[str, str]:
    headers = build_headers(bootstrap_token, category)
    headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Sec-Fetch-Storage-Access": "active",
        }
    )
    headers.pop("Content-Type", None)
    headers.pop("X-Correlation-Id", None)
    headers.pop("Traceparent", None)
    return headers


def extract_fresh_token(auth_data: Any) -> str | None:
    if not isinstance(auth_data, dict):
        return None
    candidates = [auth_data]
    for key in ("data", "result"):
        nested = auth_data.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in ("token", "access_token", "accessToken"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def refresh_auth_token(
    session: requests.Session,
    category: dict[str, str],
    bootstrap_token: str,
    current_token: str,
) -> str:
    try:
        response = session.get(
            AUTH_URL,
            headers=build_auth_headers(bootstrap_token, category),
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"Apollo auth refresh returned HTTP {response.status_code}; retrying with current token.", flush=True)
            return current_token
        fresh_token = extract_fresh_token(response.json())
        if not fresh_token:
            print("Apollo auth refresh had no recognized token field; retaining current token.", flush=True)
            return current_token
        print("Apollo auth token refreshed successfully.", flush=True)
        return fresh_token
    except (requests.RequestException, ValueError) as error:
        print(f"Apollo auth refresh failed ({type(error).__name__}); retrying with current token.", flush=True)
        return current_token


def request_page(
    session: requests.Session,
    category: dict[str, str],
    location: dict[str, Any],
    auth_state: dict[str, str],
    page_id: int,
) -> dict[str, Any]:
    variables = {
        "category_url": category["slug"],
        "page_id": page_id,
        "sort_by": "discount-DESC",
        "lat": float(location["lat"]),
        "lng": float(location["lon"]),
        "size": PAGE_SIZE,
        "pincode": str(location["pincode"]),
    }
    payload: dict[str, Any] | None = None
    bootstrap_token = auth_state["bootstrap"]
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = session.post(
                API_URL,
                headers=build_headers(auth_state["token"], category),
                json={"operationName": "getAplCategoryProducts", "variables": variables, "query": GRAPHQL_QUERY},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code in {400, 429}:
                if attempt >= MAX_REQUEST_ATTEMPTS:
                    raise CategoryRequestAborted(
                        f"Apollo page {page_id} remained HTTP {response.status_code} after {attempt} attempts"
                    )
                print(
                    f"Apollo page {page_id} returned HTTP {response.status_code}; refreshing auth before retry "
                    f"({attempt}/{MAX_REQUEST_ATTEMPTS}).",
                    flush=True,
                )
                auth_state["token"] = refresh_auth_token(
                    session, category, bootstrap_token, auth_state["token"]
                )
                if response.status_code == 429:
                    time.sleep(HTTP_429_PAUSES[min(attempt - 1, len(HTTP_429_PAUSES) - 1)])
                else:
                    time.sleep(random.uniform(*REQUEST_GAP_SECONDS))
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except CategoryRequestAborted:
            raise
        except ConsecutiveNetworkFailureLimit as error:
            raise CategoryRequestAborted(str(error)) from error
        except requests.RequestException as error:
            status = error.response.status_code if error.response is not None else None
            if attempt >= MAX_REQUEST_ATTEMPTS:
                raise
            print(
                f"HTTP/network failure for {category.get('name', category['slug'])} page {page_id} "
                f"(attempt {attempt}/{MAX_REQUEST_ATTEMPTS}, status={status}); retrying after shared wait.",
                flush=True,
            )
        except ValueError:
            raise
    if payload is None:
        raise RuntimeError(f"No Apollo response for {category['slug']} page {page_id}")
    result = (payload.get("data") or {}).get("getAplCategoryProducts")
    if not isinstance(result, dict):
        errors = payload.get("errors") or []
        raise ValueError(f"Apollo response missing getAplCategoryProducts: {errors[:1]}")
    return result


def numeric(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def product_discount(product: dict[str, Any]) -> float | None:
    discount = numeric(product.get("discount_percentage"))
    if discount is None:
        discount = numeric(product.get("discountPercentage"))
    if discount is not None:
        return discount
    mrp = numeric(product.get("mrp") or product.get("price"))
    price = numeric(product.get("special_price"))
    if mrp and price is not None:
        return max(0.0, (mrp - price) * 100 / mrp)
    return None


def availability(product: dict[str, Any]) -> str:
    status = str(product.get("status") or "").strip().lower().replace("_", "-")
    stock_flag = product.get("is_in_stock")
    if status in {"in-stock", "instock", "available"} or stock_flag in (1, True, "1", "true"):
        return "In Stock"
    if status in {"out-of-stock", "outofstock", "unavailable"} or stock_flag in (0, False, "0", "false"):
        return "Out of Stock"
    return ""


def product_to_row(product: dict[str, Any]) -> dict[str, str]:
    url_key = str(product.get("url_key") or "").strip().strip("/")
    image = str(product.get("image") or "").strip()
    if image.startswith("/"):
        image = "https://www.apollopharmacy.in" + image
    discount = product_discount(product)
    return {
        "Product ID": str(product.get("id") or "").strip(),
        "SKU": str(product.get("sku") or "").strip(),
        "Product Name": str(product.get("name") or "").strip(),
        "Brand": str(product.get("product_brand") or "").strip(),
        "MRP": str(product.get("mrp") or product.get("price") or "").strip(),
        "Price": str(product.get("special_price") or product.get("price") or "").strip(),
        "Discount %": str(round(discount, 2)) if discount is not None else "",
        "Availability": availability(product),
        "Product URL": PRODUCT_URL_BASE + url_key if url_key else "",
        "Super Category": str(product.get("classifier_1") or "").strip(),
        "Category": str(product.get("classifier_2") or "").strip(),
        "Subcategory": str(product.get("classifier_3") or product.get("subcategory") or "").strip(),
        "Discount Valid till": "",
        "Image URLs": image,
    }


def save_rows(rows: list[dict[str, str]]) -> None:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def scrape_category(
    session: requests.Session,
    category: dict[str, str],
    location: dict[str, Any],
    auth_state: dict[str, str],
) -> list[dict[str, str]]:
    try:
        first = request_page(session, category, location, auth_state, 1)
    except CategoryRequestAborted as error:
        reset_failure_counter()
        print(f"Skipping {category.get('name', category['slug'])} after consecutive request failures: {error}", flush=True)
        return []
    total_count = int(first.get("count") or 0)
    page_count = max(1, math.ceil(total_count / PAGE_SIZE))
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    page_payloads = [(1, first)]

    for page_id in range(2, page_count + 1):
        time.sleep(random.uniform(*REQUEST_GAP_SECONDS))
        try:
            page_payloads.append((page_id, request_page(session, category, location, auth_state, page_id)))
        except CategoryRequestAborted as error:
            reset_failure_counter()
            print(
                f"Stopping {category.get('name', category['slug'])} at page {page_id} "
                f"after consecutive request failures: {error}",
                flush=True,
            )
            break

    for page_id, payload in page_payloads:
        products = payload.get("products") or []
        if not isinstance(products, list):
            print(f"{category.get('name', category['slug'])}: malformed product list on page {page_id}; skipping page")
            continue
        accepted = 0
        below_threshold = 0
        for product in products:
            if not isinstance(product, dict):
                continue
            discount = product_discount(product)
            if discount is None or discount < DISCOUNT_THRESHOLD:
                below_threshold += 1
                continue
            row = product_to_row(product)
            key = row["Product ID"] or row["SKU"] or row["Product URL"]
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(row)
            accepted += 1
        print(
            f"{category.get('name', category['slug'])} | page {page_id}/{page_count} | "
            f"products={len(products)} | >=50%={accepted} | below threshold={below_threshold}",
            flush=True,
        )
    return rows


def run_sample_payload_test() -> int:
    token = get_auth_token(load_config())
    auth_state = {"bootstrap": token, "token": token}
    category = {
        "name": "Baby Care payload test",
        "slug": "baby-care",
        "url": "https://www.apollopharmacy.in/shop-by-category/baby-care",
    }
    location = {
        "lat": 19.223647947149935,
        "lon": 73.10226382004917,
        "lng": 73.10226382004917,
        "pincode": "421201",
    }
    with requests.Session() as session:
        result = request_page(session, category, location, auth_state, 1)
    products = result.get("products") or []
    print(
        f"Sample payload succeeded: category=baby-care page=1 "
        f"count={result.get('count')} products_in_page={len(products)}",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Apollo Pharmacy discounted products.")
    parser.add_argument(
        "--test-payload",
        action="store_true",
        help="Send only the supplied baby-care page 1 sample request.",
    )
    if parser.parse_args().test_payload:
        return run_sample_payload_test()

    global DISCOUNT_THRESHOLD
    config = load_config()
    threshold = numeric(config.get("discount_threshold"))
    if threshold is None:
        threshold = DISCOUNT_THRESHOLD
    DISCOUNT_THRESHOLD = threshold
    token = get_auth_token(config)
    auth_state = {"bootstrap": token, "token": token}
    location = get_location(config)
    if not all(location.get(key) not in (None, "") for key in ("lat", "lon", "pincode")):
        raise RuntimeError("Shared location must provide lat, lon, and pincode for Apollo Pharmacy.")

    categories = load_categories()
    if not categories:
        raise RuntimeError(f"No categories found in {CATEGORIES_PATH}")

    all_rows: list[dict[str, str]] = []
    with requests.Session() as session:
        for index, category in enumerate(categories, start=1):
            name = str(category.get("name") or category["slug"])
            print(f"\n[{index}/{len(categories)}] Scraping {name} ({category['slug']})", flush=True)
            rows = scrape_category(session, category, location, auth_state)
            all_rows.extend(rows)
            print(f"{name}: qualifying products={len(rows)}", flush=True)

    save_rows(all_rows)
    print(f"Saved {len(all_rows)} unique products to: {OUTPUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
