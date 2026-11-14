from __future__ import annotations

from pathlib import Path

import requests

from product_scraper import (
    API_URL,
    EXTRACTED_DIR,
    REQUEST_TIMEOUT,
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
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Authorization": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzY29wZSI6WyJwdWJsaWM6cmVhZCJdLCJqYTQiOiJxMTNkMDMxMWgzXzU1YjM3NWM1ZDIyZV82NTNkODBjM2ZlOWQiLCJ0eXBlIjoiUFVCTElDX0FDQ0VTU19UT0tFTiIsImp0aSI6IkFQMjQ3NmFmODEyZjRhN2U5ZTM3Y2I0ZGE5ODk0ekpVIiwiaXNzIjoiYXBvbGxvMjQ3LWF1dGgtc2VydmljZSIsImlhdCI6MTc5NDY0MjY3NiwiZXhwIjoxNzk0Njg1ODc2LCJhdWQiOiJodHRwczovL3d3dy5hcG9sbG9waGFybWFjeS5pbiIsInN1YiI6IjhhN2YzZWIzLTQ3MTctNDEyNC1iYzlhLWUzNGE1ZDVjZDlmOCJ9.FYWOZ10_M_Kr2rPlQK2pD2AqJ6JUervpK3UM6C5d4RADHZov_STeLkL37mYdJk_Bt3jvR4CDVmYf4VAuJkaiWT2BVHVbtPzXPot7otwrtFMb88OnwYp-Y5wWDJIaoGIW56XQrh0iNWznfikFPaS87x0EaYLlxwX6y7Bl822hjfwmRcx3Gtrd3p8RI9SE8VwNPTENqBJsAyBYgFjpElkQQD6KxkBWztEKCCkYc4b9wt9gSqpDTkK1GbVYM8ClB5Vn-68o3pUULPXVKdNXUQt8qFmE66QGioM0Je71ffBgq_dEOpcHzAinLk-uf0AWnI6NNPsF0xGdtxsv2YJd1pegAQ",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "DNT": "1",
        "Origin": "https://www.apollopharmacy.in",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": CATEGORY["url"],
        "Sec-CH-UA": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Traceparent": "00-020abd5e3a874736aad8abbac4700445-d0e39129178fa9ef-01",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "X-Correlation-Id": "null",
        "X-Device-Id": "8a7f3eb3-4717-4124-bc9a-e34a5d5cd9f8",
    }
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        response = session.post(
            API_URL,
            headers=headers,
            json=payload,
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
