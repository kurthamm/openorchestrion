#!/usr/bin/env python3
"""Check ShopGoodwill Buy Now inventory for OpenOrchestrion's top endpoint models."""

from __future__ import annotations

import json
from typing import Any

import sgw_live_scan as scan

TARGETS = [
    "Casio CTK-6200",
    "Yamaha PSR-EW300",
    "Casio WK-500",
    "Yamaha P-45B",
    "Casio CT-X700",
    "Yamaha PSR-EW310",
    "Yamaha YPG-235",
    "Yamaha PSR-E363",
    "Casio CTK-4400",
    "Casio CTK-3500",
    "Casio WK-6600",
]

_original_payload = scan.request_payload


def buy_now_payload(query: str, page: int) -> dict[str, Any]:
    p = _original_payload(query, page)
    p["searchBuyNowOnly"] = "true"
    return p


scan.request_payload = buy_now_payload


def main() -> int:
    s = scan.browser_session()
    summary: dict[str, Any] = {}
    all_items: dict[int, dict[str, Any]] = {}

    for target in TARGETS:
        try:
            items, reported, warning = scan.search_all_pages(s, target)
        except Exception as exc:
            summary[target] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"TARGET|{target}|ERROR|{type(exc).__name__}: {exc}", flush=True)
            continue

        exactish = []
        normalized_target = target.lower().replace("-", "").replace(" ", "")
        for item in items:
            title = str(item.get("title", ""))
            normalized_title = title.lower().replace("-", "").replace(" ", "")
            if normalized_target in normalized_title:
                exactish.append(item)
            if item.get("itemId"):
                all_items[int(item["itemId"])] = item

        summary[target] = {
            "reported": reported,
            "retrieved": len(items),
            "exactish": len(exactish),
            "warning": warning,
            "matches": exactish,
        }
        print(f"TARGET|{target}|reported={reported}|retrieved={len(items)}|exactish={len(exactish)}|warning={warning}", flush=True)
        for item in exactish:
            print("MATCH|" + json.dumps(item, separators=(",", ":"), default=str), flush=True)

    print("=== BUY_NOW_SUMMARY_JSON ===")
    print(json.dumps(summary, indent=2, default=str))
    print("=== END_BUY_NOW_SUMMARY_JSON ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
