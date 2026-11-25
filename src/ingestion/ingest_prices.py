import json
from pathlib import Path

from ingestion.fmp_client import fetch_daily_prices

# รายชื่อหุ้นที่ต้องการดึง (เพิ่มได้ตามต้องการ)
SYMBOLS = ["AAPL", "MSFT", "NVDA"]

START_DATE = "2025-11-18"
END_DATE = "2026-11-18"

RAW_DIR = Path("data/raw/fmp")


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failed = []

    for symbol in SYMBOLS:
        try:
            data = fetch_daily_prices(symbol, START_DATE, END_DATE)
            if not data:
                raise ValueError("ไม่พบข้อมูล")

            file_path = RAW_DIR / f"{symbol}_{START_DATE}_{END_DATE}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            print(f"[OK]   {symbol}: {len(data)} records -> {file_path}")
        except Exception as e:
            # หุ้นตัวใดตัวหนึ่งพัง ไม่ให้ทั้ง pipeline หยุด
            print(f"[FAIL] {symbol}: {e}")
            failed.append(symbol)

    if failed:
        print(f"\nล้มเหลว {len(failed)} ตัว: {failed}")


if __name__ == "__main__":
    main()
