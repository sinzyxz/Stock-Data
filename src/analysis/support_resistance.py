"""หาโซนแนวรับ/แนวต้านจากระดับราคา (Open/High/Low/Close) ที่เกิดซ้ำบ่อยในแต่ละ TF
แล้วรวมโซนข้าม TF (confluence) ถ่วงน้ำหนักตาม TF ใหญ่

หลักการต่อ 1 TF:
 1. เอาแท่งที่ 'ปิดแล้ว' เท่านั้น
 2. กว้างของ bin = BIN_ATR x ATR ของ TF นั้น (ปรับตามความผันผวนอัตโนมัติ)
 3. นับว่าแต่ละ bin ถูกแตะโดย O/H/L/C ของกี่แท่ง (แท่งเดียวนับครั้งเดียว)
 4. รวม bin ข้างเคียง (+-SMOOTH_K) แล้วหายอดสูงสุดเป็นโซน
 5. นับ touches จริงของโซน = จำนวนแท่งที่มี O/H/L/C ตกในโซน
 6. Volume ในโซน: กระจาย volume ของแต่ละแท่งเท่าๆ กันตลอดช่วง Low-High แล้วรวมเฉพาะส่วนที่อยู่ในโซน
    vol_density = สัดส่วน volume ในโซน / สัดส่วนความกว้างโซนเทียบช่วงราคาทั้งหมด
    (>1 = volume หนาแน่นกว่าค่าเฉลี่ย, >=1.5 ถือเป็นโซน volume สูง)
 คะแนนโซน = น้ำหนัก TF x touches x ตัวคูณ volume (จำกัด 0.5-2.0)
"""
import numpy as np
import pandas as pd

TF_ORDER = ["1H", "4H", "D", "W", "M", "3M", "6M", "12M"]
TF_WEIGHT = {"1H": 1, "4H": 2, "D": 3, "W": 4, "M": 5, "3M": 6, "6M": 7, "12M": 8}

MIN_BARS = 8        # จำนวนแท่งขั้นต่ำต่อ TF
WEAK_BARS = 30      # ต่ำกว่านี้ = สถิติอ่อน (เตือนผู้ใช้)
BIN_ATR = 0.25      # กว้าง 1 bin = 0.25 ATR
SMOOTH_K = 2        # โซนกว้าง ~ (2K+1) bins = 1.25 ATR
MIN_TOUCHES = 3     # ต้องถูกแตะอย่างน้อยกี่แท่งถึงนับเป็นโซน
# ค่าราคาที่ใช้นับ: ["open","high","low","close"] = โซนที่ราคาอยู่นาน (congestion)
#                   ["high","low"]               = จุดกลับตัว (เน้นปลายไส้เทียน)
PRICE_COLS = ["open", "high", "low", "close"]
VOL_MIN_F, VOL_MAX_F = 0.5, 2.0   # ขอบเขตตัวคูณ volume ต่อคะแนน
HIGH_VOL = 1.5                    # vol_density ตั้งแต่นี้ = โซน volume สูง


def avg_true_range(bars: pd.DataFrame, n: int = 14) -> float:
    pc = bars["close"].shift(1)
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - pc).abs(),
        (bars["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return float(tr.tail(n).mean())


def volume_density(bars: pd.DataFrame, lo: float, hi: float) -> float:
    """volume ที่อยู่ในโซน เทียบกับค่าเฉลี่ยถ้ากระจายเท่ากันทั้งช่วงราคา (1.0 = เท่าค่าเฉลี่ย)"""
    vol = bars["volume"].fillna(0).to_numpy(float)
    total = vol.sum()
    low_b, high_b = bars["low"].to_numpy(float), bars["high"].to_numpy(float)
    span = high_b.max() - low_b.min()
    if total <= 0 or span <= 0:
        return 1.0
    rng = high_b - low_b
    flat = rng < 1e-9
    overlap = np.clip(np.minimum(high_b, hi) - np.maximum(low_b, lo), 0, None)
    frac = np.where(flat, ((low_b >= lo) & (low_b <= hi)).astype(float),
                    overlap / np.where(flat, 1.0, rng))
    in_zone = float((vol * frac).sum())
    return (in_zone / total) / ((hi - lo) / span)


def find_zones(bars: pd.DataFrame, min_touches: int = MIN_TOUCHES) -> list:
    """bars: แท่งที่ปิดแล้ว มีคอลัมน์ ts, open, high, low, close"""
    bars = bars.reset_index(drop=True)
    if len(bars) < MIN_BARS:
        return []
    atr = avg_true_range(bars)
    if not atr > 0:
        return []

    width = atr * BIN_ATR
    pts = bars[PRICE_COLS].to_numpy(float)
    base = pts.min()
    bins = np.floor((pts - base) / width).astype(int)

    # นับต่อแท่ง: bin ที่ซ้ำกันภายในแท่งเดียวนับครั้งเดียว
    s = np.sort(bins, axis=1)
    keep = np.ones_like(s, dtype=bool)
    keep[:, 1:] = s[:, 1:] != s[:, :-1]
    counts = np.bincount(s[keep], minlength=bins.max() + 1).astype(float)

    smooth = np.convolve(counts, np.ones(2 * SMOOTH_K + 1), mode="same")

    zones, suppressed = [], np.zeros(len(smooth), dtype=bool)
    for idx in np.argsort(-smooth):
        if smooth[idx] < min_touches:
            break
        if suppressed[idx]:
            continue
        suppressed[max(0, idx - 2 * SMOOTH_K): idx + 2 * SMOOTH_K + 1] = True

        lo = base + (idx - SMOOTH_K) * width
        hi = base + (idx + SMOOTH_K + 1) * width
        inside = (pts >= lo) & (pts <= hi)
        touched = inside.any(axis=1)
        touches = int(touched.sum())
        if touches < min_touches:
            continue
        zones.append({
            "lo": float(lo), "hi": float(hi),
            "center": float(pts[inside].mean()),
            "touches": touches,
            "last_touch": bars.loc[touched, "ts"].max(),
            "vol_density": volume_density(bars, lo, hi),
        })
    return zones


def merge_zones(zones: list) -> list:
    """รวมโซนที่ซ้อนทับกันข้าม TF: คะแนนรวมกัน แต่ขอบโซนยึดตามโซนที่คะแนนสูงสุด"""
    zs = sorted(zones, key=lambda z: -z["score"])
    used = [False] * len(zs)
    merged = []
    for i, z in enumerate(zs):
        if used[i]:
            continue
        members, used[i] = [z], True
        for j in range(i + 1, len(zs)):
            if not used[j] and zs[j]["lo"] <= z["hi"] and zs[j]["hi"] >= z["lo"]:
                members.append(zs[j])
                used[j] = True
        score = sum(m["score"] for m in members)
        tfs = sorted({m["tf"] for m in members}, key=TF_ORDER.index)
        merged.append({
            # ใช้ขอบของโซนที่แข็งแรงที่สุดเป็นหลัก (ไม่รวมขอบทั้งหมด เพราะจะบวมจนใช้ไม่ได้)
            "lo": z["lo"],
            "hi": z["hi"],
            "center": sum(m["center"] * m["score"] for m in members) / score,
            "score": score,
            "vol_density": sum(m["vol_density"] * m["score"] for m in members) / score,
            "timeframes": ",".join(tfs),
            "touches": ",".join(f"{m['tf']}:{m['touches']}"
                                for m in sorted(members, key=lambda m: TF_ORDER.index(m["tf"]))),
            "n_tf": len(tfs),
        })
    return merged


def analyze(bars_by_tf: dict, ref_price: float):
    """bars_by_tf: {tf: DataFrame ของแท่งที่ปิดแล้ว}  คืน (DataFrame โซน, รายการเตือน)"""
    all_zones, warnings = [], []
    for tf in TF_ORDER:
        bars = bars_by_tf.get(tf)
        if bars is None or len(bars) < MIN_BARS:
            warnings.append(f"{tf}: ข้อมูลไม่พอ ({0 if bars is None else len(bars)} แท่ง) ข้ามไป")
            continue
        if len(bars) < WEAK_BARS:
            warnings.append(f"{tf}: มีเพียง {len(bars)} แท่ง สถิติอ่อน ควรดึงข้อมูลย้อนหลังเพิ่ม")
        for z in find_zones(bars):
            vol_f = float(np.clip(z["vol_density"], VOL_MIN_F, VOL_MAX_F))
            z.update(tf=tf, score=TF_WEIGHT[tf] * z["touches"] * vol_f)
            all_zones.append(z)

    merged = merge_zones(all_zones)
    df = pd.DataFrame(merged)
    if df.empty:
        return df, warnings

    df["high_volume"] = df["vol_density"] >= HIGH_VOL
    df["type"] = np.where(df["center"] < ref_price, "support", "resistance")
    df["distance_pct"] = (df["center"] - ref_price) / ref_price * 100
    df["ref_price"] = ref_price
    return df.sort_values("score", ascending=False).reset_index(drop=True), warnings


def entry_signal(bars: pd.DataFrame, zones: pd.DataFrame,
                 lookback: int = 5, min_drop_atr: float = 1.5, top_n: int = 15,
                 min_score_ratio: float = 0.25) -> pd.DataFrame:
    """เงื่อนไขเข้าซื้อหลังแท่งปิด (ตรวจกับแท่งที่ปิดล่าสุดของ TF นั้น):
      1. แท่งล่าสุดเป็นแท่งเขียว และแท่งก่อนหน้าเป็นแท่งแดง
      2. ก่อนหน้านั้นเป็นขาลงจริง: ราคาปิดลดลงอย่างน้อย min_drop_atr x ATR ภายใน lookback แท่ง
      3. ใช้เฉพาะโซนที่คะแนน >= min_score_ratio ของโซนที่แข็งแรงที่สุด (ตัดโซนอ่อนที่เกิดจากราคาแค่วิ่งผ่าน)
      4. ไส้ล่างของแท่งเขียวแตะ/ทะลุโซนแนวรับ (โซนที่ขอบล่างอยู่ใต้ราคาปิดแท่งก่อนหน้า) แต่ราคาปิดไม่หลุดขอบล่างโซน
    ไม่เข้าเงื่อนไข = ไม่ซื้อ (เช่น กำลังเขียววิ่งขึ้น ไม่ได้ลงมาที่แนวรับ)
    """
    empty = zones.iloc[0:0]
    bars = bars.reset_index(drop=True)
    if zones.empty or len(bars) < lookback + 3:
        return empty

    last, prev = bars.iloc[-1], bars.iloc[-2]
    if not (last["close"] > last["open"] and prev["close"] < prev["open"]):
        return empty

    atr = avg_true_range(bars)
    drop = bars["close"].iloc[-lookback - 2] - prev["close"]
    if not (atr > 0 and drop >= min_drop_atr * atr):
        return empty

    # โซนที่อยู่ใต้ราคา หรือราคาลงมาอยู่ในโซน/ต่ำกว่าขอบล่างเล็กน้อย (ผ่อนผัน 1 ATR)
    strong = zones[zones["score"] >= min_score_ratio * zones["score"].max()]
    sup = strong[strong["lo"] < prev["close"] + atr].head(top_n)
    # ไส้ล่างลงไปแตะ/ทะลุโซน แต่ราคาปิดกลับมายืนในหรือเหนือโซน
    hit = sup[(last["low"] <= sup["hi"]) & (last["close"] >= sup["lo"])]
    return hit.sort_values("score", ascending=False)