#!/usr/bin/env python3

import json
import time
from pathlib import Path
import sys

import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.utils import normalize_symbol

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

from config import DEFAULT_HEADERS
HEADERS = DEFAULT_HEADERS

def determine_instrument_type(ins_id: str, symbol: str, name: str) -> str:
    if not ins_id or len(ins_id) < 12:
        return 'unknown'
        
    prefix = ins_id[:3]
    
    if prefix == 'IRO':
        return 'stock'
    elif prefix == 'IRT':
        return 'etf'
    elif prefix == 'IRR':
        if 'ح' in symbol and 'حق تقدم' in name:
            return 'right'
        else:
            return 'option'
    elif prefix == 'IRB':
        return 'bond'
    elif prefix in ('IRU', 'IRM'):
        return 'commodity'
        
    return 'unknown'

def get_market_name(ins_id: str) -> str:
    if not ins_id or len(ins_id) < 4:
        return "نامشخص"
    prefix = ins_id[:4]
    
    prefixes = {
        "IRO1": "بورس",
        "IRO3": "فرابورس",
        "IRO7": "بازار پایه فرابورس",
        "IRO2": "بورس کالا",
        "IRO4": "بورس انرژی",
        "IRR1": "اختیار معامله / حق تقدم بورس",
        "IRR3": "اختیار معامله / حق تقدم فرابورس",
        "IRT1": "صندوق بورس",
        "IRT3": "صندوق فرابورس",
    }
    return prefixes.get(prefix, f"سایر ({prefix})")


TSE_SECTORS = {
    "10": "استخراج زغال سنگ",
    "11": "کشاورزی، دامپروری",
    "13": "استخراج کانه های فلزی",
    "14": "استخراج سایر معادن",
    "17": "منسوجات",
    "19": "دباغی، پرداخت چرم و ساخت انواع پاپوش",
    "20": "محصولات چوبی",
    "21": "محصولات کاغذی",
    "22": "انتشار، چاپ و تکثیر",
    "23": "فراورده های نفتی، کک و سوخت هسته ای",
    "25": "لاستیک و پلاستیک",
    "26": "تولید محصولات کامپیوتری الکترونیکی ونوری",
    "27": "فلزات اساسی",
    "28": "ساخت محصولات فلزی",
    "29": "ماشین آلات و تجهیزات",
    "31": "ماشین آلات و دستگاه‌های برقی",
    "32": "ساخت دستگاه‌ها و وسایل ارتباطی",
    "33": "ابزارپزشکی، اپتیکی و اندازه گیری",
    "34": "خودرو و ساخت قطعات",
    "35": "سایر وسایل نقلیه",
    "36": "مبلمان و مصنوعات دیگر",
    "38": "قند و شکر",
    "39": "شرکت های چند رشته ای صنعتی",
    "40": "عرضه برق، گاز، بخار و آب گرم",
    "42": "ساخت رادیو، تلویزیون و دستگاه‌ها و وسایل ارتباطی",
    "43": "انبوه سازی، املاک و مستغلات",
    "44": "محصولات شیمیایی",
    "45": "پیمانکاری صنعتی",
    "47": "تجارت خرده فروشی",
    "49": "حمل و نقل، انبارداری و ارتباطات",
    "50": "خرده فروشی",
    "53": "سیمان، آهک و گچ",
    "54": "کاشی و سرامیک",
    "55": "هتل و رستوران",
    "56": "سرمایه گذاری ها",
    "57": "بانک ها و موسسات اعتباری",
    "58": "سایر واسطه گریهای مالی",
    "59": "بیمه و صندوق بازنشستگی به جز تامین اجتماعی",
    "60": "فعالیتهای کمکی به نهادهای مالی واسط",
    "61": "صندوق سرمایه گذاری قابل معامله",
    "64": "مخابرات",
    "65": "فعالیت های پشتیبانی و کمکی حمل و نقل",
    "66": "فعالیتهای پشتيباني و کمکي حمل و نقل",
    "67": "اوراق تامین مالی",
    "68": "صندوق سرمایه گذاری قابل معامله",
    "69": "صندوق سرمایه گذاری در املاک و مستغلات",
    "70": "اطلاعات و ارتباطات",
    "71": "اوراق حق تقدم تسهیلات مسکن",
    "72": "خدمات فنی و مهندسی",
    "73": "فعالیتهای حرفه ای، علمی و فنی",
    "74": "فعالیتهای جنبی واسطه گریهای مالی",
    "82": "سایر فعالیت های خدماتی",
    "90": "سایر فعالیتها",
    "93": "مواد و محصولات دارویی",
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

        if len(ins_id) < 8:
            continue

        if not ins_code or ins_code == "0":
            continue

        symbol = normalize_symbol(row.get("lva"))
        if not symbol:
            symbol = ""

        if symbol.endswith('3'):
            continue

        name = row.get("lvc") or ""
        
        # We classify everything, don't silently drop based on prefix/suffix anymore
        market = get_market_name(ins_id)
        inst_type = determine_instrument_type(ins_id, symbol, name)
        
        # User explicitly requested: "ببین من فقط نمادهای تابلو اول و دوم و فرابورس و باراز پایه رو میخوام. اختیار و این ها رو نمیخوام."
        # Allowed prefixes: 
        # IRO1 (بورس), IRO3 (فرابورس), IRO7 (بازار پایه)
        # IRT1 (صندوق بورس), IRT3 (صندوق فرابورس) - We'll keep ETFs just in case, but definitely exclude IRR, IRU, IRB, etc.
        prefix = ins_id[:4]
        if prefix not in ('IRO1', 'IRO3', 'IRO7', 'IRT1', 'IRT3'):
            # Allow rights in Bourse and Farabourse, but strictly exclude options (which are also IRR)
            if prefix in ('IRR1', 'IRR3') and inst_type == 'right':
                pass
            else:
                continue

        sector_code = str(row.get("csv", "")).strip()
        sector_name = TSE_SECTORS.get(sector_code, f"گروه {sector_code}" if sector_code else "ناشناخته")

        instrument = {
            "ins_code": ins_code,
            "ins_id": ins_id,
            "symbol": normalize_symbol(symbol),
            "name": name,
            "sector_code": sector_code,
            "sector_name": sector_name,
            "market": market,
            "market_board": None, # Could map from cgrValCotTitle if available
            "isin": None,
            "instrument_type": inst_type
        }

        instruments.append(instrument)

    # Prevent duplicate ins_code
    unique = {}
    for item in instruments:
        unique[item["ins_code"]] = item

    instruments = list(unique.values())
    instruments.sort(key=lambda x: x["symbol"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(instruments, f, ensure_ascii=False, indent=2)

    # Insert/Update directly to Database
    db = DatabaseManager()
    with db.connect() as conn:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        db_records = []
        for inst in instruments:
            db_records.append((
                inst['ins_code'], inst['ins_id'], inst['isin'], inst['symbol'], inst['name'],
                inst['sector_code'], inst['sector_name'],
                inst['market'], inst['market_board'], inst['instrument_type'],
                1, now, now, now # active=1, created_at, updated_at, last_seen_at
            ))
            
        conn.executemany("""
            INSERT INTO instruments (
                ins_code, ins_id, isin, symbol, name, sector_code, sector_name, market, market_board, instrument_type, 
                active, created_at, updated_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ins_code) DO UPDATE SET
                ins_id = excluded.ins_id,
                isin = excluded.isin,
                symbol = excluded.symbol,
                name = excluded.name,
                sector_code = excluded.sector_code,
                sector_name = excluded.sector_name,
                market = excluded.market,
                instrument_type = excluded.instrument_type,
                active = 1,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
        """, db_records)
        
        # Mark unseen instruments as inactive
        # Any instrument not seen in this run gets active=0
        ins_codes = [inst['ins_code'] for inst in instruments]
        placeholders = ','.join(['?'] * len(ins_codes))
        
        # We don't disable everything, just update status for this run
        conn.execute(f"UPDATE instruments SET active = 0 WHERE ins_code NOT IN ({placeholders})", ins_codes)
        
        conn.commit()

    print()
    print("=" * 50)
    print("DONE")
    print("=" * 50)
    print(f"Output : {OUTPUT_FILE}")
    print(f"Total  : {len(instruments)}")

    print()
    print("By Type:")
    type_counts = {}
    for x in instruments:
        t = x["instrument_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    
    for t, c in sorted(type_counts.items()):
        print(f"  {t:<15} {c}")

    print()
    print("First 10:")
    for item in instruments[:10]:
        print(f"  {item['symbol']:<15} {item['instrument_type']:<10} {item['ins_code']}")

if __name__ == "__main__":
    main()