
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAW_DAILY_DIR = Path("data/raw/fmp")
RAW_INTRADAY_DIR = Path("data/raw/fmp_intraday")
OUT_DIR = Path("data/processed/bars")

MARKET_TZ = ZoneInfo("America/New_York")  # FMP intraday ใช้เวลาตลาดสหรัฐ
INTRADAY = {"1H": ("1hour", pd.Timedelta(hours=1)), "4H": ("4hour", pd.Timedelta(hours=4))}
RESAMPLED = ["W", "M", "3M", "6M", "12M"]
COLS = ["open", "high", "low", "close", "volume"]
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def read_json_files(paths) -> pd.DataFrame:
    frames = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            frames.append(pd.DataFrame(json.load(f)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["ts"] = pd.to_datetime(df["date"])
    for c in COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.drop_duplicates(subset="ts", keep="last").sort_values("ts")
    return df[["ts"] + COLS].reset_index(drop=True)


def period_end(index: pd.DatetimeIndex, tf: str) -> pd.DatetimeIndex:
    if tf == "W":
        return index.to_period("W-FRI").end_time.normalize()
    if tf == "M":
        return index.to_period("M").end_time.normalize()
    if tf == "3M":
        return index.to_period("Q").end_time.normalize()
    if tf == "12M":
        return index.to_period("Y").end_time.normalize()
    if tf == "6M":
        return pd.DatetimeIndex([
            pd.Timestamp(y, 6, 30) if m <= 6 else pd.Timestamp(y, 12, 31)
            for y, m in zip(index.year, index.month)
        ])
    raise ValueError(tf)


def _complete(pe: pd.Timestamp, last: pd.Timestamp) -> bool:
    if pe <= last:
        return True
    # งวดจบวันเสาร์/อาทิตย์ และวันซื้อขายสุดท้ายคือศุกร์ก่อนหน้า
    return pe.weekday() >= 5 and (pe - last).days <= 2 and last.weekday() == 4


def resample_daily(daily: pd.DataFrame, tf: str) -> pd.DataFrame:
    df = daily.copy()
    df["pe"] = period_end(pd.DatetimeIndex(df["ts"]), tf)
    g = df.groupby("pe").agg(ts=("ts", "first"), **{c: (c, AGG[c]) for c in COLS})
    g = g.reset_index()
    last = df["ts"].max()
    g["is_complete"] = g["pe"].apply(lambda pe: _complete(pe, last))
    return g.drop(columns="pe")


def intraday_bars(raw: pd.DataFrame, duration: pd.Timedelta) -> pd.DataFrame:
    df = prepare(raw)
    now = pd.Timestamp.now(tz=MARKET_TZ).tz_localize(None)
    df["is_complete"] = (df["ts"] + duration) <= now
    return df


def build_symbol(symbol: str, daily_dir=RAW_DAILY_DIR, intraday_dir=RAW_INTRADAY_DIR) -> dict:
    out = {}

    daily_raw = read_json_files(sorted(Path(daily_dir).glob(f"{symbol}_*.json")))
    if not daily_raw.empty:
        daily = prepare(daily_raw)
        d = daily.copy()
        d["is_complete"] = True
        out["D"] = d
        for tf in RESAMPLED:
            out[tf] = resample_daily(daily, tf)

    for tf, (interval, dur) in INTRADAY.items():
        files = sorted(Path(intraday_dir).glob(f"{symbol}_{interval}_*.json"))
        if files:
            out[tf] = intraday_bars(read_json_files(files), dur)

    for tf, df in out.items():
        df.insert(0, "timeframe", tf)
        df.insert(0, "symbol", symbol)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    symbols = sorted({p.stem.split("_")[0] for p in RAW_DAILY_DIR.glob("*.json")})
    if not symbols:
        raise FileNotFoundError(f"ไม่พบไฟล์ raw ใน {RAW_DAILY_DIR}")

    for symbol in symbols:
        for tf, df in build_symbol(symbol).items():
            df.to_csv(OUT_DIR / f"{symbol}_{tf}.csv", index=False)
            done = int(df["is_complete"].sum())
            print(f"[OK] {symbol} {tf:>3}: {len(df):>5} bars (ปิดแล้ว {done})")


if __name__ == "__main__":
    main()