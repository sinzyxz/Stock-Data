
import json
from pathlib import Path

from ingestion.fmp_client import fetch_daily_prices


# กำหนดหุ้นที่ต้องการทดลอง
symbol = "NVDA"

# กำหนดช่วงเวลาที่ต้องการ
start_date = "2025-11-18"
end_date = "2026-11-18"


# เรียกฟังก์ชันเพื่อดึงข้อมูลจาก FMP
data = fetch_daily_prices(
    symbol=symbol,
    start_date=start_date,
    end_date=end_date
)

# ตรวจสอบว่ามีข้อมูลหรือไม่
if not data:
    raise ValueError(f"ไม่พบข้อมูลหุ้น {symbol}")

# สร้างโฟลเดอร์สำหรับเก็บ Raw Data
raw_dir = Path("data/raw/fmp")
raw_dir.mkdir(parents=True, exist_ok=True)

# สร้างชื่อไฟล์
file_path = raw_dir / f"{symbol}_{start_date}_{end_date}.json"

# บันทึก JSON ลงไฟล์
with open(file_path, "w", encoding="utf-8") as file:
    json.dump(data, file, indent=4, ensure_ascii=False)

# แสดงผลการทำงาน
print("========== FMP DATA INGESTION ==========")
print(f"Symbol: {symbol}")
print(f"Total Records: {len(data)}")
print(f"Saved File: {file_path}")

print("\nFirst Record:")
print(json.dumps(data[0], indent=4))
