"""สั่งรัน pipeline ทั้งชุด

  python main.py                    # รันทุกขั้นตอน ยกเว้น 1H/4H
  python main.py --with-intraday    # รวมการดึง 1H/4H
  python main.py --steps build quality_files   # รันเฉพาะบางขั้นตอน

หุ้นและช่วงวันที่ตั้งค่าที่ ingestion/ingest_prices.py และ ingestion/ingest_intraday.py
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analysis import run_zones
from ingestion import ingest_intraday, ingest_prices
from load import load_bars
from quality import data_quality
from transform import build_bars


STEPS = [
    ("daily", "ดึง Daily จาก FMP", ingest_prices.main),
    ("intraday", "ดึง 1H/4H จาก FMP", ingest_intraday.main),
    ("build", "สร้างแท่งเทียนทุก Timeframe", build_bars.main),
    ("quality_files", "ตรวจคุณภาพข้อมูล (ไฟล์ CSV)",
     lambda: data_quality.main("files")),
    ("load", "โหลดเข้า Postgres", load_bars.main),
    ("quality_db", "ตรวจคุณภาพข้อมูล (Postgres)",
     lambda: data_quality.main("postgres")),
    ("zones", "หาโซนแนวรับต้านและสัญญาณ", run_zones.main),
]

LOG_PATH = Path("logs/pipeline_runs.jsonl")


def write_run_log(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    names = [step[0] for step in STEPS]
    parser = argparse.ArgumentParser(description="Stock data pipeline")
    parser.add_argument(
        "--with-intraday",
        action="store_true",
        help="รวมขั้นตอนดึง 1H/4H",
    )
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=names,
        help="รันเฉพาะขั้นตอนที่ระบุ",
    )
    args = parser.parse_args()

    selected = [step for step in STEPS if not args.steps or step[0] in args.steps]

    # ถ้าไม่ได้ระบุ --steps ให้ข้าม intraday เว้นแต่สั่ง --with-intraday
    if not args.with_intraday and not args.steps:
        selected = [step for step in selected if step[0] != "intraday"]

    for i, (name, desc, func) in enumerate(selected, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(selected)}] {name}: {desc}\n{'=' * 60}")
        started_at = datetime.now(timezone.utc)

        try:
            func()
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            write_run_log({
                "step": name,
                "status": "failed",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "error": str(e),
            })
            print(f"\n[STOP] ขั้นตอน '{name}' ล้มเหลว: {e}")
            raise SystemExit(1)
        else:
            finished_at = datetime.now(timezone.utc)
            write_run_log({
                "step": name,
                "status": "success",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
            })
            elapsed = (finished_at - started_at).total_seconds()
            print(f"[DONE] {name} ({elapsed:.1f}s)")

    print("\nPipeline เสร็จสมบูรณ์")


if __name__ == "__main__":
    main()