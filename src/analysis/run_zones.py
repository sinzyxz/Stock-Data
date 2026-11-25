"""อ่านแท่งเทียนจาก Postgres -> หาโซนแนวรับ/ต้าน -> บันทึกตาราง sr_zones"""
import pandas as pd
from psycopg2.extras import execute_values

from analysis.support_resistance import TF_ORDER, analyze, entry_signal
from load.load_postgres import get_connection

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sr_zones (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20) NOT NULL,
    zone_type    VARCHAR(12) NOT NULL,
    lo           NUMERIC(18, 4),
    hi           NUMERIC(18, 4),
    center       NUMERIC(18, 4),
    score        NUMERIC(12, 2),
    n_tf         INT,
    timeframes   TEXT,
    touches      TEXT,
    distance_pct NUMERIC(10, 3),
    ref_price    NUMERIC(18, 4),
    computed_at  TIMESTAMP DEFAULT NOW()
);
ALTER TABLE sr_zones ADD COLUMN IF NOT EXISTS vol_density NUMERIC(10, 3);
ALTER TABLE sr_zones ADD COLUMN IF NOT EXISTS high_volume BOOLEAN;
"""
COLS = ["ts", "open", "high", "low", "close", "volume"]


def load_bars(cur, symbol, tf):
    cur.execute(
        "SELECT ts, open, high, low, close, volume FROM price_bars "
        "WHERE symbol=%s AND timeframe=%s AND is_complete ORDER BY ts",
        (symbol, tf),
    )
    df = pd.DataFrame(cur.fetchall(), columns=COLS)
    df[COLS[1:]] = df[COLS[1:]].astype(float)
    return df


def main():
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.execute("SELECT DISTINCT symbol FROM price_bars ORDER BY symbol")
            symbols = [r[0] for r in cur.fetchall()]

            for symbol in symbols:
                bars = {tf: load_bars(cur, symbol, tf) for tf in TF_ORDER}
                daily = bars["D"]
                if daily.empty:
                    print(f"[SKIP] {symbol}: ไม่มี Daily")
                    continue

                last_bar = daily.iloc[-1]
                zones, warns = analyze(bars, ref_price=float(last_bar["close"]))
                print(f"\n===== {symbol} | แท่ง D ล่าสุดที่ปิด {last_bar['ts']:%Y-%m-%d} "
                      f"close={last_bar['close']:.2f} =====")
                for w in warns:
                    print("  [WARN]", w)
                if zones.empty:
                    print("  ไม่พบโซน")
                    continue

                cur.execute("DELETE FROM sr_zones WHERE symbol=%s", (symbol,))
                rows = [(symbol, z.type, z.lo, z.hi, z.center, z.score, z.n_tf,
                         z.timeframes, z.touches, z.distance_pct, z.ref_price,
                         z.vol_density, bool(z.high_volume))
                        for z in zones.itertuples()]
                execute_values(cur, """
                    INSERT INTO sr_zones (symbol, zone_type, lo, hi, center, score, n_tf,
                                          timeframes, touches, distance_pct, ref_price,
                                          vol_density, high_volume)
                    VALUES %s""", rows)

                cols = ["type", "lo", "hi", "score", "vol_density", "high_volume",
                        "timeframes", "distance_pct"]
                print(zones.head(8)[cols].round(2).to_string(index=False))

                # สแกนสัญญาณเข้าซื้อ (หลังแท่งปิด) ทุก TF ที่มีข้อมูล
                found = False
                for tf in TF_ORDER:
                    b = bars[tf]
                    if b.empty:
                        continue
                    hit = entry_signal(b, zones)
                    if not hit.empty:
                        found = True
                        print(f"  >> สัญญาณ [{tf}] แท่งปิด {b.iloc[-1]['ts']}: เขียวต่อจากแดงขาลง แตะโซนรับ")
                        print(hit.head(3)[["lo", "hi", "score", "vol_density", "timeframes"]]
                              .round(2).to_string(index=False))
                if not found:
                    print("  (ยังไม่มีสัญญาณเข้าซื้อในทุก TF)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
