"""ดึงข้อมูล 1H / 4H จาก FMP (Premium endpoint) แล้วเก็บเป็น raw JSON"""
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from ingestion.fmp_client import API_KEY, BASE_URL

SYMBOLS = ["AAPL", "MSFT", "NVDA"]
INTERVALS = ["1hour", "4hour"]

# ย้อนหลังได้แค่ไหนขึ้นกับแพ็กเกจ FMP ของคุณ ปรับตามต้องการ
START_DATE = "2025-01-01"
END_DATE = date.today().isoformat()

CHUNK_DAYS = 30  # แบ่งขอทีละ 30 วัน กัน API ตัดข้อมูล
RAW_DIR = Path("data/raw/fmp_intraday")


def date_chunks(start: str, end: str, days: int):
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    while cur <= stop:
        nxt = min(cur + timedelta(days=days - 1), stop)
        yield cur.isoformat(), nxt.isoformat()
        cur = nxt + timedelta(days=1)


def fetch_intraday(symbol: str, interval: str, start: str, end: str) -> list:
    if not API_KEY:
        raise ValueError("ไม่พบ FMP_API_KEY ในไฟล์ .env")

    rows = []
    for s, e in date_chunks(start, end, CHUNK_DAYS):
        resp = requests.get(
            f"{BASE_URL}/historical-chart/{interval}",
            params={"symbol": symbol, "from": s, "to": e, "apikey": API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"API ส่งข้อมูลไม่ใช่ List: {data}")
        rows.extend(data)
        time.sleep(0.2)  # เว้นจังหวะ กันโดน rate limit

    # ตัดแถวซ้ำจากรอยต่อของแต่ละช่วง
    unique = {r["date"]: r for r in rows}
    return [unique[k] for k in sorted(unique)]


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            try:
                data = fetch_intraday(symbol, interval, START_DATE, END_DATE)
                if not data:
                    raise ValueError("ไม่พบข้อมูล")
                path = RAW_DIR / f"{symbol}_{interval}_{START_DATE}_{END_DATE}.json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                print(f"[OK]   {symbol} {interval}: {len(data)} bars -> {path}")
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                hint = " (แพ็กเกจฟรีไม่รองรับ intraday)" if code == 402 else ""
                print(f"[FAIL] {symbol} {interval}: HTTP {code}{hint}")
            except Exception as e:
                print(f"[FAIL] {symbol} {interval}: {e}")


if __name__ == "__main__":
    main()
