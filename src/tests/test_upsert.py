import uuid

import pandas as pd
from psycopg2.extras import execute_values

from load.load_bars import CREATE_SQL, UPSERT_SQL, get_connection, to_rows


def test_upsert_updates_existing_bar_instead_of_duplicating():
    symbol = "TEST_" + uuid.uuid4().hex[:8]
    ts = pd.Timestamp("2024-01-02 00:00:00")

    first = pd.DataFrame([{
        "symbol": symbol,
        "timeframe": "D",
        "ts": ts,
        "open": 10,
        "high": 12,
        "low": 9,
        "close": 11,
        "volume": 100,
        "is_complete": True,
    }])

    updated = first.copy()
    updated["close"] = 11.5

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_SQL)

                execute_values(cur, UPSERT_SQL, to_rows(first))
                execute_values(cur, UPSERT_SQL, to_rows(updated))

                cur.execute(
                    """
                    SELECT COUNT(*), MAX(close)
                    FROM price_bars
                    WHERE symbol = %s AND timeframe = 'D' AND ts = %s
                    """,
                    (symbol, ts),
                )
                count, close = cur.fetchone()

        assert count == 1
        assert float(close) == 11.5
    finally:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM price_bars WHERE symbol = %s",
                    (symbol,),
                )
        conn.close()