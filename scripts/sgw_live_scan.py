#!/usr/bin/env python3
"""Reproducible live ShopGoodwill sweep for OpenOrchestrion MIDI endpoints.

The scan starts from the current inventory, not remembered favorite models. It runs
multiple overlapping musical-keyboard searches against ShopGoodwill's live Buyer API,
paginates each result set, detects broken/repeating pagination, deduplicates by item ID,
removes obvious accessories/non-musical keyboards, and emits a compact candidate set.

Inventory triage is intentionally separate from the procurement gate. Finalists still
require manufacturer evidence for inbound MIDI, multitimbral/GM behavior, controllers,
program changes, polyphony, and audio output.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests

SEARCH_URL = "https://buyerapi.shopgoodwill.com/api/Search/ItemListing"

# Coverage arms, not ranking priors. Overlap is deliberate; item IDs are deduplicated.
QUERIES = [
    "digital piano",
    "electronic piano",
    "portable keyboard",
    "electronic musical keyboard",
    "arranger keyboard",
    "music keyboard",
    "Yamaha keyboard",
    "Yamaha PSR",
    "Yamaha DGX",
    "Yamaha YPG",
    "Casio keyboard",
    "Casio CTK",
    "Casio CT X",
    "Casio WK keyboard",
    "Casio Privia",
    "Roland keyboard",
    "Korg keyboard",
    "Kawai keyboard",
    "Kurzweil keyboard",
]

NEGATIVE_TITLE = re.compile(
    r"\b(?:stand|bench|case|bag|cover|pedal|adapter|power supply|charger|cable|manual|"
    r"sheet music|book|computer keyboard|wireless keyboard|gaming keyboard|typewriter|"
    r"keycaps?|mouse|laptop|keyboard tray|keyboard drawer|controller only|midi controller)\b",
    re.I,
)
MUSICAL_HINT = re.compile(
    r"\b(?:piano|keyboard|synth|synthesizer|workstation|arranger|organ|PSR|DGX|YPG|"
    r"CTK|CT-X|CTX|WK-?\d|Privia|Fantom|Juno|Motif)\b",
    re.I,
)


def browser_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://shopgoodwill.com",
        "Referer": "https://shopgoodwill.com/",
    })
    return s


def request_payload(query: str, page: int) -> dict[str, Any]:
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
        "sortColumn": "1",          # ending soonest
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


def search_all_pages(s: requests.Session, query: str) -> tuple[list[dict[str, Any]], int, str | None]:
    out: list[dict[str, Any]] = []
    seen_page_fingerprints: set[tuple[int, ...]] = set()
    total = 0
    warning = None

    for page in range(1, 51):
        r = s.post(SEARCH_URL, json=request_payload(query, page), timeout=30)
        r.raise_for_status()
        sr = r.json().get("searchResults", {})
        items = sr.get("items", []) or []
        total = int(sr.get("itemCount", 0) or 0)
        if not items:
            break

        fingerprint = tuple(int(x.get("itemId", 0) or 0) for x in items)
        if fingerprint in seen_page_fingerprints:
            warning = f"pagination repeated at page {page}; stopped safely"
            break
        seen_page_fingerprints.add(fingerprint)
        out.extend(items)

        if len(items) < 40 or len({int(x.get('itemId', 0) or 0) for x in out}) >= total:
            break
        time.sleep(0.03)
    else:
        warning = "50-page safety cap reached"

    # A malformed API total must never manufacture duplicate inventory.
    unique = {int(i.get("itemId")): i for i in out if i.get("itemId")}
    return list(unique.values()), total, warning


def price_number(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 999999.0


def triage_score(title: str) -> int:
    """Broad capability prior only; manufacturer documentation decides the finalists."""
    t = title.lower()
    score = 0
    if any(b in t for b in ("yamaha", "casio", "roland", "korg", "kawai", "kurzweil")):
        score += 5
    # Arranger / workstation families are particularly interesting because OpenOrchestrion
    # benefits from multitimbral program/channel playback, not merely piano key feel.
    strong_patterns = [
        r"psr[- ](?:s|sx)\d", r"psr[- ]ew\d", r"dgx[- ]\d", r"ypg[- ]\d",
        r"ct[- ]?x\d", r"ctk[- ](?:6|7)\d{3}", r"wk[- ]\d",
        r"\bbk[- ]\d", r"\be[- ]\d{2,}", r"\bpa\d{2,}",
        r"motif", r"fantom", r"juno", r"kurzweil",
    ]
    for p in strong_patterns:
        if re.search(p, t):
            score += 15
            break
    medium_patterns = [r"psr[- ]e\d", r"ctk[- ]\d", r"privia", r"px[- ]\d"]
    for p in medium_patterns:
        if re.search(p, t):
            score += 8
            break
    if "with power" in t or "power adapter" in t or "ac adapter" in t:
        score += 2
    if "tested" in t or "working" in t:
        score += 3
    if "for parts" in t or "not working" in t or "untested" in t:
        score -= 8
    return score


def main() -> int:
    s = browser_session()
    merged: dict[int, dict[str, Any]] = {}
    matched_by: dict[int, set[str]] = {}
    coverage: dict[str, Any] = {}

    for q in QUERIES:
        try:
            items, total, warning = search_all_pages(s, q)
        except Exception as exc:
            coverage[q] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"COVERAGE_ERROR {q!r}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            continue
        coverage[q] = {"reported": total, "retrievedUnique": len(items), "warning": warning}
        print(f"COVERAGE {q!r}: reported={total}, unique={len(items)}, warning={warning}", flush=True)
        for item in items:
            try:
                iid = int(item.get("itemId"))
            except (TypeError, ValueError):
                continue
            merged[iid] = item
            matched_by.setdefault(iid, set()).add(q)

    if not merged:
        print("No live inventory returned from any coverage arm", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    for iid, item in merged.items():
        title = str(item.get("title", ""))
        if NEGATIVE_TITLE.search(title) or not MUSICAL_HINT.search(title):
            continue
        rows.append({
            "itemId": iid,
            "title": title,
            "currentPrice": item.get("currentPrice"),
            "numBids": item.get("numBids"),
            "endTime": item.get("endTime"),
            "remainingTime": item.get("remainingTime"),
            "sellerName": item.get("sellerName") or item.get("seller") or item.get("sellerTitle"),
            "shippingPrice": item.get("shippingPrice") or item.get("shippingCost"),
            "pickupOnly": item.get("isPickupOnly") or item.get("pickupOnly"),
            "imageURL": item.get("imageURL"),
            "url": f"https://shopgoodwill.com/item/{iid}",
            "matchedQueries": sorted(matched_by.get(iid, set())),
            "triageScore": triage_score(title),
        })

    # We emit all plausible musical endpoints, but sort interesting families first and cheaper
    # current bids second. Final selection is not made by this score.
    rows.sort(key=lambda x: (-x["triageScore"], price_number(x.get("currentPrice")), str(x.get("endTime") or "")))

    summary = {
        "generatedAtUTC": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverageArms": len(QUERIES),
        "uniqueInventoryBeforeFilter": len(merged),
        "plausibleMusicalEndpoints": len(rows),
        "coverage": coverage,
    }
    print("\n=== SGW_SCAN_SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    print("=== SGW_CANDIDATES_JSON ===")
    print(json.dumps(rows, indent=2, default=str))
    print("=== END_SGW_CANDIDATES_JSON ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
