"""สั่งรัน pipeline ทั้งชุด

  python main.py                    # รันทุกขั้นตอน ยกเว้น 1H/4H (แพ็กเกจฟรีของ FMP ไม่รองรับ)
  python main.py --with-intraday    # รวมการดึง 1H/4H (ต้องใช้แพ็กเกจที่รองรับ)
  python main.py --steps build quality_files   # รันเฉพาะบางขั้นตอน

หุ้นและช่วงวันที่ตั้งค่าที่ ingestion/ingest_prices.py และ ingestion/ingest_intraday.py
"""
import argparse
import time

from analysis import run_zones
from ingestion import ingest_intraday, ingest_prices
from load import load_bars
from quality import data_quality
from transform import build_bars

# (ชื่อขั้นตอน, คำอธิบาย, ฟังก์ชัน)
STEPS = [
    ("daily",         "ดึง Daily จาก FMP",                 ingest_prices.main),
    ("intraday",      "ดึง 1H/4H จาก FMP",                 ingest_intraday.main),
    ("build",         "สร้างแท่งเทียนทุก Timeframe",         build_bars.main),
    ("quality_files", "ตรวจคุณภาพข้อมูล (ไฟล์ CSV)",      lambda: data_quality.main("files")),
    ("load",          "โหลดเข้า Postgres",                  load_bars.main),
    ("quality_db",    "ตรวจคุณภาพข้อมูล (Postgres)",         lambda: data_quality.main("postgres")),
    ("zones",         "หาโซนแนวรับต้านและสัญญาณ",            run_zones.main),
]


def main():
    names = [s[0] for s in STEPS]
    parser = argparse.ArgumentParser(description="Stock data pipeline")
    parser.add_argument("--with-intraday", action="store_true", help="รวมขั้นตอนดึง 1H/4H")
    parser.add_argument("--steps", nargs="+", choices=names, help="รันเฉพาะขั้นตอนที่ระบุ")
    args = parser.parse_args()

    selected = [s for s in STEPS if not args.steps or s[0] in args.steps]
    # intraday เป็น opt-in ยกเว้นสั่งเจาะจงด้วย --steps intraday
    if not args.with_intraday and not args.steps:
        selected = [s for s in selected if s[0] != "intraday"]

    for i, (name, desc, func) in enumerate(selected, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(selected)}] {name}: {desc}\n{'=' * 60}")
        start = time.time()
        try:
            func()
        except Exception as e:
            print(f"\n[STOP] ขั้นตอน '{name}' ล้มเหลว: {e}")
            raise SystemExit(1)
        print(f"[DONE] {name} ({time.time() - start:.1f}s)")

    print("\nPipeline เสร็จสมบูรณ์")


if __name__ == "__main__":
    main()