"""โหลดแท่งเทียนทุก TF เข้า Postgres ตาราง price_bars (upsert)"""
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

from load.load_postgres import get_connection

BARS_DIR = Path("data/processed/bars")
COLUMNS = ["symbol", "timeframe", "ts", "open", "high", "low", "close", "volume", "is_complete"]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS price_bars (
    symbol      VARCHAR(20) NOT NULL,
    timeframe   VARCHAR(5)  NOT NULL,
    ts          TIMESTAMP   NOT NULL,
    open        NUMERIC(18, 4),
    high        NUMERIC(18, 4),
    low         NUMERIC(18, 4),
    close       NUMERIC(18, 4),
    volume      BIGINT,
    is_complete BOOLEAN NOT NULL,
    loaded_at   TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, timeframe, ts)
);
"""

UPSERT_SQL = f"""
INSERT INTO price_bars ({", ".join(COLUMNS)}) VALUES %s
ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
    close = EXCLUDED.close, volume = EXCLUDED.volume,
    is_complete = EXCLUDED.is_complete, loaded_at = NOW();
"""


def to_rows(df: pd.DataFrame):
    df = df[COLUMNS].astype(object)
    df = df.where(df.notna(), None)
    return df.values.tolist()


def main():
    files = sorted(BARS_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"ไม่พบไฟล์ใน {BARS_DIR} (รัน transform.build_bars ก่อน)")

    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            for path in files:
                rows = to_rows(pd.read_csv(path, parse_dates=["ts"]))
                execute_values(cur, UPSERT_SQL, rows, page_size=2000)
                print(f"[OK] {path.name}: {len(rows)} rows")

            cur.execute("""
                SELECT timeframe, COUNT(*), MIN(ts), MAX(ts)
                FROM price_bars GROUP BY timeframe ORDER BY timeframe
            """)
            print("\ntimeframe | bars | first | last")
            for r in cur.fetchall():
                print(" | ".join(str(x) for x in r))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
