"""ตรวจคุณภาพข้อมูลแท่งเทียน (price_bars) ก่อนนำไปวิเคราะห์

รัน:
  python -m quality.data_quality            # อ่านจาก Postgres (ตาราง price_bars)
  python -m quality.data_quality files      # อ่านจากไฟล์ CSV ใน data/processed/bars (ก่อนโหลดเข้า DB)

ตรวจต่อ (symbol, timeframe):
  - จำนวนแท่ง / ปิดแล้วกี่แท่ง / ช่วงวันที่ / ครอบคลุมกี่ปี
  - ค่าว่างใน OHLC, ราคา <= 0, volume เป็น 0
  - OHLC ผิดตรรกะ (high ต่ำกว่า open/close/low หรือ low สูงกว่า open/close/high)
  - ts ซ้ำ
  - ช่องว่างข้อมูลยาวผิดปกติ (D/1H/4H) และราคาปิดกระโดดแรง (อาจเป็น stock split หรือข้อมูลผิด)
  - ข้อมูลพอสำหรับวิเคราะห์แนวรับต้านหรือไม่ (อิงเกณฑ์เดียวกับ analysis)
"""
import sys
from pathlib import Path

import pandas as pd

from analysis.support_resistance import MIN_BARS, TF_ORDER, WEAK_BARS

BARS_DIR = Path("data/processed/bars")
REPORT_PATH = Path("data/quality_report.csv")
GAP_DAYS = 5        # ช่องว่างเกินกี่วันถึงผิดปกติ (วันหยุดยาวปกติไม่เกิน 4 วัน)
JUMP_PCT = 20.0     # ราคาปิดเปลี่ยนเกินกี่ % ต่อแท่งถึงน่าสงสัย
CHECK_GAP_JUMP = {"1H", "4H", "D"}  # TF ใหญ่ ช่องว่าง/การเปลี่ยนแปลงสูงเป็นเรื่องปกติ


def profile(df: pd.DataFrame, tf: str):
    """คืน (สรุปเป็น dict, รายละเอียดแถวที่มีปัญหา)"""
    df = df.sort_values("ts").reset_index(drop=True)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    ohlc = df[["open", "high", "low", "close"]]

    bad_ohlc = (h < pd.concat([o, c, l], axis=1).max(axis=1)) | \
               (l > pd.concat([o, c, h], axis=1).min(axis=1))
    nonpos = (ohlc <= 0).any(axis=1)
    zero_vol = df["volume"].fillna(0) == 0
    dup_ts = df["ts"].duplicated(keep=False)

    gaps = pd.Series(False, index=df.index)
    jumps = pd.Series(False, index=df.index)
    if tf in CHECK_GAP_JUMP:
        gaps = df["ts"].diff().dt.days > GAP_DAYS
        jumps = (c.pct_change().abs() * 100) > JUMP_PCT

    complete = int(df["is_complete"].sum())
    span_years = (df["ts"].max() - df["ts"].min()).days / 365.25 if len(df) > 1 else 0.0

    if complete < MIN_BARS:
        sr_ready = "SKIP"      # น้อยเกินไป ระบบข้าม TF นี้
    elif complete < WEAK_BARS:
        sr_ready = "WEAK"      # สถิติอ่อน
    else:
        sr_ready = "OK"

    n_null = int(ohlc.isna().any(axis=1).sum())
    summary = {
        "symbol": df["symbol"].iloc[0], "timeframe": tf,
        "bars": len(df), "complete": complete,
        "first": df["ts"].min(), "last": df["ts"].max(),
        "years": round(span_years, 1),
        "null_ohlc": n_null, "bad_ohlc": int(bad_ohlc.sum()), "nonpos": int(nonpos.sum()),
        "zero_vol": int(zero_vol.sum()), "dup_ts": int(dup_ts.sum()),
        "gaps": int(gaps.sum()), "jumps": int(jumps.sum()),
        "sr_ready": sr_ready,
    }
    hard = ["null_ohlc", "bad_ohlc", "nonpos", "dup_ts"]
    soft = ["gaps", "jumps"]
    summary["status"] = ("ERROR" if any(summary[k] for k in hard)
                         else "CHECK" if any(summary[k] for k in soft) else "OK")

    details = {
        "OHLC ผิดตรรกะ": df[bad_ohlc], "ราคา <= 0": df[nonpos],
        "ts ซ้ำ": df[dup_ts], "ช่องว่างข้อมูลยาว": df[gaps], "ราคากระโดดแรง": df[jumps],
    }
    return summary, details


def load_files() -> pd.DataFrame:
    files = sorted(BARS_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"ไม่พบไฟล์ใน {BARS_DIR} (รัน transform.build_bars ก่อน)")
    return pd.concat([pd.read_csv(f, parse_dates=["ts"]) for f in files], ignore_index=True)


def load_postgres() -> pd.DataFrame:
    from load.load_postgres import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol, timeframe, ts, open, high, low, close, volume, is_complete "
                        "FROM price_bars")
            cols = [d[0] for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def main(source: str = "postgres"):
    df = load_files() if source == "files" else load_postgres()
    print(f"แหล่งข้อมูล: {source} | ทั้งหมด {len(df):,} แถว\n")

    rows, all_details = [], {}
    for (symbol, tf), g in df.groupby(["symbol", "timeframe"]):
        s, d = profile(g, tf)
        rows.append(s)
        all_details[(symbol, tf)] = d

    report = pd.DataFrame(rows)
    report["_o"] = report["timeframe"].map({t: i for i, t in enumerate(TF_ORDER)})
    report = report.sort_values(["symbol", "_o"]).drop(columns="_o").reset_index(drop=True)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    show = report.copy()
    show["first"] = show["first"].dt.strftime("%Y-%m-%d")
    show["last"] = show["last"].dt.strftime("%Y-%m-%d")
    print(show.to_string(index=False))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)
    print(f"\nบันทึกรายงานที่ {REPORT_PATH}")

    # แสดงตัวอย่างแถวที่มีปัญหา (ไม่เกิน 3 แถวต่อประเภท)
    for (symbol, tf), details in all_details.items():
        for name, rows_ in details.items():
            if not rows_.empty:
                print(f"\n[{symbol} {tf}] {name}: {len(rows_)} แถว (ตัวอย่าง)")
                print(rows_[["ts", "open", "high", "low", "close", "volume"]].head(3).to_string(index=False))

    print("\nสรุป:",
          f"ERROR {int((report.status == 'ERROR').sum())} | "
          f"CHECK {int((report.status == 'CHECK').sum())} | "
          f"OK {int((report.status == 'OK').sum())} กลุ่ม")
    weak = report[report.sr_ready != "OK"]
    if not weak.empty:
        print("TF ที่ข้อมูลยังไม่พอสำหรับหาแนวรับต้าน:",
              ", ".join(f"{r.symbol} {r.timeframe}({r.sr_ready}, {r.complete} แท่ง)" for r in weak.itertuples()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "postgres")
