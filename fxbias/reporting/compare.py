from __future__ import annotations

from typing import Dict, Optional

import pandas as pd


PILLAR_COLS = ("rates", "growth", "risk", "positioning")


def _bias_col(df: pd.DataFrame) -> str:
    return "final_bias" if "final_bias" in df.columns else "bias"


def _score_col(df: pd.DataFrame) -> str:
    return "total_score" if "total_score" in df.columns else "score"


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    x = panel.copy()
    x["pair"] = x["pair"].astype(str).str.upper()
    x["as_of"] = x["as_of"].astype(str)
    return x.sort_values(["pair", "as_of"], kind="mergesort").reset_index(drop=True)


def classify_flip(bias_a: Optional[str], bias_b: Optional[str]) -> str:
    a = str(bias_a or "")
    b = str(bias_b or "")
    if not a or not b or a == b:
        return ""
    if a == "BULL_BASE" and b == "BEAR_BASE":
        return "BULL->BEAR"
    if a == "BEAR_BASE" and b == "BULL_BASE":
        return "BEAR->BULL"
    if b == "NEUTRAL":
        return "->NEUTRAL"
    return "CHANGED"


def persistence_streak(panel: pd.DataFrame, as_of_b: str) -> Dict[str, int]:
    x = _normalize_panel(panel)
    bcol = _bias_col(x)
    out: Dict[str, int] = {}

    for pair, g in x.groupby("pair", sort=True):
        hist = g[g["as_of"] <= str(as_of_b)].sort_values("as_of", ascending=False)
        if hist.empty:
            out[pair] = 0
            continue
        anchor = str(hist.iloc[0].get(bcol) or "")
        streak = 0
        for _, row in hist.iterrows():
            if str(row.get(bcol) or "") != anchor:
                break
            streak += 1
        out[pair] = streak
    return out


def build_compare_table(panel: pd.DataFrame, as_of_a: str, as_of_b: str) -> pd.DataFrame:
    x = _normalize_panel(panel)
    bcol = _bias_col(x)
    scol = _score_col(x)

    a_rows = x[x["as_of"] == str(as_of_a)].set_index("pair")
    b_rows = x[x["as_of"] == str(as_of_b)].set_index("pair")
    pairs = sorted(set(a_rows.index.tolist()) | set(b_rows.index.tolist()))
    streaks = persistence_streak(x, as_of_b)

    out_rows = []
    for pair in pairs:
        ra = a_rows.loc[pair] if pair in a_rows.index else None
        rb = b_rows.loc[pair] if pair in b_rows.index else None

        row = {
            "pair": pair,
            "as_of_a": str(as_of_a),
            "as_of_b": str(as_of_b),
            "bias_a": None if ra is None else ra.get(bcol),
            "bias_b": None if rb is None else rb.get(bcol),
            "flip": classify_flip(None if ra is None else ra.get(bcol), None if rb is None else rb.get(bcol)),
            "persistence_b": int(streaks.get(pair, 0)),
        }

        def delta(col: str) -> Optional[float]:
            va = None if ra is None else pd.to_numeric(ra.get(col), errors="coerce")
            vb = None if rb is None else pd.to_numeric(rb.get(col), errors="coerce")
            if pd.isna(va) or pd.isna(vb):
                return None
            return float(vb - va)

        for col in PILLAR_COLS:
            row[f"delta_{col}"] = delta(col)
        row["delta_total_score"] = delta(scol)
        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    if out.empty:
        return out
    return out.sort_values(["pair"], kind="mergesort").reset_index(drop=True)


def build_compare_payload(panel: pd.DataFrame, as_of_a: str, as_of_b: str) -> dict:
    table = build_compare_table(panel=panel, as_of_a=as_of_a, as_of_b=as_of_b)
    flips = table["flip"].fillna("").astype(str)
    return {
        "as_of_a": str(as_of_a),
        "as_of_b": str(as_of_b),
        "rows": table.to_dict(orient="records"),
        "flip_counts": {
            "BULL->BEAR": int((flips == "BULL->BEAR").sum()),
            "BEAR->BULL": int((flips == "BEAR->BULL").sum()),
            "->NEUTRAL": int((flips == "->NEUTRAL").sum()),
            "CHANGED": int((flips == "CHANGED").sum()),
        },
    }

