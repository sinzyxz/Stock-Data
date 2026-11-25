import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/fmp")
PROCESSED_DIR = Path("data/processed/fmp")

NUMERIC_COLS = ["open", "high", "low", "close", "volume", "change", "change_percent", "vwap"]


def load_raw(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"changePercent": "change_percent"})

    # แปลงชนิดข้อมูล
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ลบข้อมูลซ้ำและแถวที่ไม่มีราคาปิด
    df = df.drop_duplicates(subset=["symbol", "date"], keep="last")
    df = df.dropna(subset=["symbol", "date", "close"])

    # Data quality check: high ต้อง >= low
    bad = df[df["high"] < df["low"]]
    if not bad.empty:
        print(f"  [WARN] พบ {len(bad)} แถวที่ high < low (ตัดออก)")
        df = df.drop(bad.index)

    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for path in sorted(RAW_DIR.glob("*.json")):
        df = clean(load_raw(path))
        out = PROCESSED_DIR / f"{path.stem}.parquet"
        df.to_parquet(out, index=False)
        print(f"[OK] {path.name}: {len(df)} rows -> {out}")


if __name__ == "__main__":
    main()
