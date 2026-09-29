#!/usr/bin/env python3

import json
import time
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

OUTPUT_FILE = DATA_DIR / "instruments.json"

URL = (
    "https://cdn.tsetmc.com/api/ClosingPrice/"
    "GetMarketWatch"
    "?market=0"
    "&paperTypes[0]=1"
    "&paperTypes[1]=2"
    "&paperTypes[2]=3"
    "&paperTypes[3]=4"
    "&paperTypes[4]=5"
    "&paperTypes[5]=6"
    "&paperTypes[6]=7"
    "&paperTypes[7]=8"
    "&paperTypes[8]=9"
    "&withBestLimits=false"
    "&hEven=0"
    "&RefID=0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

TARGET_PREFIXES = {
    "IRO1": "بورس",
    "IRO3": "فرابورس",
    "IRO7": "بازار پایه فرابورس",
}


def fetch_marketwatch():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return data["marketwatch"]


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching TSETMC MarketWatch...")

    rows = fetch_marketwatch()

    print(f"MarketWatch records: {len(rows)}")

    instruments = []

    for row in rows:
        ins_id = str(row.get("insID") or "")
        ins_code = str(row.get("insCode") or "")

        # فقط سهام عادی:
        # IRO1 / IRO3 / IRO7
        # و instrument اصلی با suffix = 0001
        if len(ins_id) < 8:
            continue

        prefix = ins_id[:4]

        if prefix not in TARGET_PREFIXES:
            continue

        if not ins_id.endswith("0001"):
            continue

        if not ins_code or ins_code == "0":
            continue

        symbol = row.get("lva")

        if not symbol:
            symbol = ""

        instrument = {
            "ins_code": ins_code,
            "ins_id": ins_id,
            "symbol": symbol,
            "name": row.get("lvc"),
            "market": TARGET_PREFIXES[prefix],
            "market_board": None,
            "isin": None,
        }

        instruments.append(instrument)

    # جلوگیری از duplicate
    unique = {}

    for item in instruments:
        unique[item["ins_code"]] = item

    instruments = list(unique.values())

    instruments.sort(
        key=lambda x: x["symbol"]
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            instruments,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 50)
    print("DONE")
    print("=" * 50)
    print(f"Output : {OUTPUT_FILE}")
    print(f"Total  : {len(instruments)}")

    print()
    print("By market:")

    for market in TARGET_PREFIXES.values():
        count = sum(
            1
            for x in instruments
            if x["market"] == market
        )

        print(f"  {market:<25} {count}")

    print()
    print("First 10:")

    for item in instruments[:10]:
        print(
            f"  {item['symbol']:<15} "
            f"{item['ins_id']} "
            f"{item['ins_code']}"
        )


if __name__ == "__main__":
    main()