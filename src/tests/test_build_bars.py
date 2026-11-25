import pandas as pd

from transform.build_bars import prepare


def test_prepare_sorts_rows_and_keeps_latest_duplicate():
    df = pd.DataFrame([
        {"date": "2024-01-02", "open": "10", "high": "12",
         "low": "9", "close": "11", "volume": "100"},
        {"date": "2024-01-02", "open": "10", "high": "13",
         "low": "9", "close": "12", "volume": "110"},
        {"date": "2024-01-01", "open": "8", "high": "10",
         "low": "7", "close": "9", "volume": "90"},
    ])

    result = prepare(df)

    assert len(result) == 2
    assert result["ts"].is_monotonic_increasing
    assert result.iloc[-1]["close"] == 12