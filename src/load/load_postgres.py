import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

PROCESSED_DIR = Path("data/processed/fmp")

COLUMNS = [
    "symbol", "date", "open", "high", "low", "close",
    "volume", "change", "change_percent", "vwap",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_prices (
    symbol         VARCHAR(20) NOT NULL,
    date           DATE        NOT NULL,
    open           NUMERIC(18, 4),
    high           NUMERIC(18, 4),
    low            NUMERIC(18, 4),
    close          NUMERIC(18, 4),
    volume         BIGINT,
    change         NUMERIC(18, 4),
    change_percent NUMERIC(18, 6),
    vwap           NUMERIC(18, 4),
    loaded_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, date)
);
"""

# ถ้า (symbol, date) ซ้ำ ให้อัปเดตค่าใหม่ -> รันซ้ำได้ ไม่เกิดข้อมูลซ้ำ
UPSERT_SQL = f"""
INSERT INTO daily_prices ({", ".join(COLUMNS)})
VALUES %s
ON CONFLICT (symbol, date) DO UPDATE SET
    open           = EXCLUDED.open,
    high           = EXCLUDED.high,
    low            = EXCLUDED.low,
    close          = EXCLUDED.close,
    volume         = EXCLUDED.volume,
    change         = EXCLUDED.change,
    change_percent = EXCLUDED.change_percent,
    vwap           = EXCLUDED.vwap,
    loaded_at      = NOW();
"""


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def to_rows(df: pd.DataFrame):
    # เติมคอลัมน์ที่ไม่มีเป็น None และแปลง NaN -> None (psycopg2 ไม่รับ NaN เป็น NULL)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNS].astype(object)
    df = df.where(df.notna(), None)
    return df.values.tolist()


def main():
    files = sorted(PROCESSED_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"ไม่พบไฟล์ Parquet ใน {PROCESSED_DIR}")

    conn = get_connection()
    try:
        with conn:  # commit อัตโนมัติ / rollback ถ้า error
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE_SQL)

                for path in files:
                    rows = to_rows(pd.read_parquet(path))
                    execute_values(cur, UPSERT_SQL, rows, page_size=1000)
                    print(f"[OK] {path.name}: {len(rows)} rows")

                cur.execute("""
                    SELECT symbol, COUNT(*), MIN(date), MAX(date)
                    FROM daily_prices GROUP BY symbol ORDER BY symbol
                """)
                print("\nsymbol | days | first_day | last_day")
                for row in cur.fetchall():
                    print(" | ".join(str(x) for x in row))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
