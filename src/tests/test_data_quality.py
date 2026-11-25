import pandas as pd

from quality.data_quality import profile


def test_profile_flags_bad_ohlc_and_duplicate_timestamp():
    df = pd.DataFrame([
        {
            "symbol": "TEST",
            "timeframe": "D",
            "ts": "2024-01-02",
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "volume": 100,
            "is_complete": True,
        },
        {
            "symbol": "TEST",
            "timeframe": "D",
            "ts": "2024-01-02",
            "open": 10,
            "high": 8,
            "low": 9,
            "close": 11,
            "volume": 100,
            "is_complete": True,
        },
    ])
    df["ts"] = pd.to_datetime(df["ts"])

    summary, _ = profile(df, "D")

    assert summary["dup_ts"] == 2
    assert summary["bad_ohlc"] == 1
    assert summary["status"] == "ERROR"