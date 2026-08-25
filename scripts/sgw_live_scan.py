#!/usr/bin/env python3
"""Live, reproducible ShopGoodwill inventory sweep for OpenOrchestrion endpoints.

This intentionally does not start from previously favored models. It queries overlapping
musical-keyboard terms against ShopGoodwill's live Buyer API, paginates every result set,
deduplicates by item ID, removes obvious non-instruments/accessories, and prints a machine-
readable candidate set for a second-stage capability review.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from typing import Any

import requests

API_ROOT = "https://buyerapi.shopgoodwill.com/api"
SEARCH_URL = f"{API_ROOT}/Search/ItemListing"
DETAIL_URL = f"{API_ROOT}/ItemDetail/GetItemDetailModelByItemId"

# Deliberately overlapping and model-diverse. Brand/model-family searches are coverage arms,
# not ranking priors. The merged result set is deduplicated before scoring.
QUERIES = [
    "digital piano",
    "electronic piano",
    "portable keyboard",
    "electronic musical keyboard",
    "arranger keyboard",
    "music keyboard",
    "Yamaha PSR",
    "Yamaha DGX",
    "Yamaha YPG",
    "Casio CTK",
    "Casio CT-X",
    "Casio WK keyboard",
    "Casio Privia",
    "Roland keyboard",
    "Korg keyboard",
    "Kawai keyboard",
    "Kurzweil keyboard",
]

# Strong evidence an item is not the self-contained MIDI sound endpoint we need.
NEGATIVE_TITLE = re.compile(
    r"\b(?:stand|bench|case|bag|cover|pedal|adapter|power supply|charger|cable|manual|"
    r"sheet music|book|computer keyboard|wireless keyboard|gaming keyboard|typewriter|"
    r"keycaps?|mouse|laptop|controller only|midi controller)\b",
    re.I,
)

MUSICAL_HINT = re.compile(
    r"\b(?:piano|keyboard|synth|synthesizer|workstation|arranger|organ|PSR|DGX|YPG|CTK|CT-X|WK-|Privia)\b",
    re.I,
)

# Inventory triage only. Final procurement gating is done against manufacturer MIDI docs.
def inventory_score(item: dict[str, Any], detail_text: str = "") -> int:
    text = f"{item.get('title', '')} {detail_text}".lower()
    score = 0
    if "usb" in text: score += 8
    if "midi" in text: score += 10
    if "general midi" in text or " gm " in f" {text} ": score += 8
    if "tested" in text or "works" in text or "working" in text: score += 5
    if "power adapter" in text or "ac adapter" in text or "power supply" in text: score += 3
    if any(x in text for x in ("76 key", "76-key", "88 key", "88-key")): score += 2
    # Families commonly capable of being self-contained multitimbral sound engines.
    if any(x in text for x in ("psr-", "dgx-", "ypg-", "ctk-", "ct-x", "wk-", "roland", "korg", "kurzweil")):
        score += 3
    return score


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://shopgoodwill.com",
        "Referer": "https://shopgoodwill.com/",
    })
    return s


def payload(query: str, page: int) -> dict[str, Any]:
    return {
        "isSize": False,
        "isWeddingCatagory": "false",
        "isMultipleCategoryIds": False,
        "isFromHeaderMenuTab": False,
        "layout": "",
        "isFromHomePage": False,
        "searchText": query,
        "selectedGroup": "",
        "selectedCategoryIds": "",
        "selectedSellerIds": "",
        "lowPrice": "0",
        "highPrice": "999999",
        "searchBuyNowOnly": "",
        "searchPickupOnly": "false",
        "searchNoPickupOnly": "false",
        "searchOneCentShippingOnly": "false",
        "searchDescriptions": "true",
        "searchClosedAuctions": "false",
        "closedAuctionEndingDate": datetime.now().strftime("%m/%d/%Y"),
        "closedAuctionDaysBack": "7",
        "searchCanadaShipping": "false",
        "searchInternationalShippingOnly": "false",
        "sortColumn": "1",           # ending soonest
        "sortDescending": "false",
        "savedSearchId": 0,
        "useBuyerPrefs": "true",
        "searchUSOnlyShipping": "false",
        "categoryLevelNo": "1",
        "partNumber": "",
        "catIds": "",
        "categoryLevel": 1,
        "categoryId": 0,
        "page": page,
        "pageSize": 40,
    }


def live_search(s: requests.Session, query: str) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    page = 1
    total = 0
    while True:
        r = s.post(SEARCH_URL, json=payload(query, page), timeout=30)
        r.raise_for_status()
        body = r.json().get("searchResults", {})
        items = body.get("items", []) or []
        total = int(body.get("itemCount", 0) or 0)
        out.extend(items)
        if not items or len(items) < 40 or len(out) >= total:
            break
        page += 1
        if page > 100:
            raise RuntimeError(f"Pagination safety limit hit for query {query!r}")
        time.sleep(0.05)
    return out, total


def get_detail_text(s: requests.Session, item_id: int) -> str:
    try:
        r = s.get(f"{DETAIL_URL}/{item_id}", timeout=20)
        r.raise_for_status()
        data = r.json()
        # Preserve all scalar text because API field names have changed over time.
        chunks: list[str] = []
        def walk(v: Any) -> None:
            if isinstance(v, dict):
                for x in v.values(): walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
            elif isinstance(v, str):
                chunks.append(v)
        walk(data)
        return " ".join(chunks)
    except Exception as exc:
        return f"DETAIL_ERROR {type(exc).__name__}: {exc}"


def main() -> int:
    s = session()
    merged: dict[int, dict[str, Any]] = {}
    coverage: dict[int, set[str]] = {}
    query_counts: dict[str, int] = {}

    for q in QUERIES:
        try:
            items, total = live_search(s, q)
        except Exception as exc:
            print(f"SEARCH_ERROR {q!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        query_counts[q] = total
        print(f"COVERAGE {q!r}: {total} live results", flush=True)
        for item in items:
            try:
                iid = int(item.get("itemId"))
            except (TypeError, ValueError):
                continue
            merged[iid] = item
            coverage.setdefault(iid, set()).add(q)

    candidates: list[dict[str, Any]] = []
    for iid, item in merged.items():
        title = str(item.get("title", ""))
        if NEGATIVE_TITLE.search(title):
            continue
        if not MUSICAL_HINT.search(title):
            continue
        candidates.append(item)

    # Pull detail text for every plausible instrument. This lets us distinguish "powers on"
    # and included adapters from title-only guesses while keeping final MIDI capability gating
    # separate and evidence-based.
    enriched = []
    for n, item in enumerate(candidates, 1):
        iid = int(item["itemId"])
        detail = get_detail_text(s, iid)
        row = {
            "itemId": iid,
            "title": item.get("title"),
            "currentPrice": item.get("currentPrice"),
            "numBids": item.get("numBids"),
            "endTime": item.get("endTime"),
            "remainingTime": item.get("remainingTime"),
            "sellerName": item.get("sellerName") or item.get("seller") or item.get("sellerTitle"),
            "shippingPrice": item.get("shippingPrice") or item.get("shippingCost"),
            "pickupOnly": item.get("isPickupOnly") or item.get("pickupOnly"),
            "imageURL": item.get("imageURL"),
            "url": f"https://shopgoodwill.com/item/{iid}",
            "matchedQueries": sorted(coverage.get(iid, set())),
            "inventoryScore": inventory_score(item, detail),
            "detailExcerpt": re.sub(r"\s+", " ", detail)[:1800],
        }
        enriched.append(row)
        if n % 20 == 0:
            print(f"DETAIL_PROGRESS {n}/{len(candidates)}", flush=True)
        time.sleep(0.03)

    enriched.sort(key=lambda x: (-x["inventoryScore"], str(x.get("endTime") or ""), float(x.get("currentPrice") or 0)))

    print("\n=== SGW_SCAN_SUMMARY ===")
    print(json.dumps({
        "queries": len(QUERIES),
        "queryCounts": query_counts,
        "uniqueItemsBeforeFilter": len(merged),
        "plausibleMusicalEndpoints": len(enriched),
        "generatedAtUTC": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }, indent=2, default=str))
    print("=== SGW_CANDIDATES_JSON ===")
    print(json.dumps(enriched, indent=2, default=str))
    print("=== END_SGW_CANDIDATES_JSON ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
