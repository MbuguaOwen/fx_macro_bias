from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
from dateutil import parser as date_parser


OPTIONS_COLUMNS = [
    "put_delta",
    "put_price",
    "strike",
    "call_price",
    "call_delta",
    "imp_vol",
]

_HEADER_ALIASES = {
    "put_delta": {"putdelta", "putdlt", "putdel", "pdelta"},
    "put_price": {"putprice", "putprem", "putpremium", "put"},
    "strike": {"strike", "strk"},
    "call_price": {"callprice", "callprem", "callpremium", "call"},
    "call_delta": {"calldelta", "calldlt", "calldel", "cdelta"},
    "imp_vol": {"impvol", "impliedvolatility", "impliedvol", "iv", "impv"},
}

_MISSING_TOKENS = {"", "-", "--", "n/a", "na", "null", "none"}


def _normalize_header(text: str) -> str:
    text = (text or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _to_float(text: object) -> Optional[float]:
    raw = str(text or "").strip()
    if not raw:
        return None
    clean = raw.replace(",", "").replace("%", "").replace("−", "-").strip()
    if clean.lower() in _MISSING_TOKENS:
        return None
    neg = clean.startswith("(") and clean.endswith(")")
    clean = clean.strip("()")
    m = re.search(r"-?\d+(?:\.\d+)?", clean)
    if not m:
        return None
    out = float(m.group(0))
    return -abs(out) if neg else out


def _extract_symbol(text: str, url: str) -> str:
    upper = (text or "").upper()
    pair = re.search(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", upper)
    if pair:
        return f"{pair.group(1)}{pair.group(2)}"
    compact = re.search(r"\b([A-Z]{6})\b", upper)
    if compact:
        return compact.group(1)
    return _guess_symbol_from_url(url) or "UNKNOWN"


def _guess_symbol_from_url(url: str) -> Optional[str]:
    lower = (url or "").lower()
    m = re.search(r"/([a-z]{3})-([a-z]{3})-options", lower)
    if m:
        return f"{m.group(1)}{m.group(2)}".upper()
    m = re.search(r"/([a-z]{6})-options", lower)
    if m:
        return m.group(1).upper()
    return None


def _extract_spot(text: str) -> Optional[float]:
    patterns = [
        r"(?:spot|last|price)\s*[:=]?\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:spot|last)\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return _to_float(m.group(1))
    return None


def _extract_expiry_date(text: str) -> Optional[dt.date]:
    patterns = [
        r"(?:expiry|expiration|expires)\s*[:=]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"(?:expiry|expiration|expires)\s*[:=]?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{4})",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return date_parser.parse(m.group(1), dayfirst=False).date()
        except Exception:
            continue
    return None


def _header_map(headers: Iterable[str]) -> Dict[str, int]:
    normalized = [_normalize_header(h) for h in headers]
    out: Dict[str, int] = {}
    for idx, col in enumerate(normalized):
        for target, aliases in _HEADER_ALIASES.items():
            if col in aliases:
                out[target] = idx
                break
    return out if all(c in out for c in OPTIONS_COLUMNS) else {}


def _parse_tables_with_regex(html: str) -> tuple[list[list[str]], str]:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)
        clean_cells = [re.sub(r"<[^>]+>", " ", c) for c in cells]
        clean_cells = [re.sub(r"\s+", " ", c).strip() for c in clean_cells]
        if clean_cells:
            rows.append(clean_cells)
    return rows, text


def parse_options_surface_html(url: str, html: str, tenor: str = "1M") -> pd.DataFrame:
    """Parse an Investing options table from static HTML into a normalized surface dataframe."""
    best_rows = []
    page_text = ""
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html or "", "html.parser")
        page_text = soup.get_text(" ", strip=True)

        for table in soup.find_all("table"):
            headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
            map_idx = _header_map(headers)
            parsed_rows = []
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if not cells:
                    continue
                vals = [c.get_text(" ", strip=True) for c in cells]
                row: Dict[str, Optional[float]] = {}

                if map_idx:
                    for col, idx in map_idx.items():
                        row[col] = _to_float(vals[idx]) if idx < len(vals) else None
                else:
                    nums = [_to_float(v) for v in vals]
                    nums = [x for x in nums if x is not None]
                    if len(nums) < 6:
                        continue
                    row = dict(zip(OPTIONS_COLUMNS, nums[:6]))

                if row.get("strike") is None or row.get("imp_vol") is None:
                    continue
                parsed_rows.append(row)

            if len(parsed_rows) > len(best_rows):
                best_rows = parsed_rows
    except ImportError:
        rows, page_text = _parse_tables_with_regex(html)
        if rows:
            headers = rows[0]
            map_idx = _header_map(headers)
            body = rows[1:]
            for vals in body:
                row: Dict[str, Optional[float]] = {}
                if map_idx:
                    for col, idx in map_idx.items():
                        row[col] = _to_float(vals[idx]) if idx < len(vals) else None
                else:
                    nums = [_to_float(v) for v in vals]
                    nums = [x for x in nums if x is not None]
                    if len(nums) < 6:
                        continue
                    row = dict(zip(OPTIONS_COLUMNS, nums[:6]))
                if row.get("strike") is None or row.get("imp_vol") is None:
                    continue
                best_rows.append(row)

    if not best_rows:
        return pd.DataFrame(columns=OPTIONS_COLUMNS + ["symbol", "spot", "expiry_date", "days_to_expiry", "tenor", "source_url"])

    df = pd.DataFrame(best_rows)
    for c in OPTIONS_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "put_delta" in df.columns:
        df["put_delta"] = df["put_delta"].map(lambda x: None if pd.isna(x) else -abs(float(x)))
    if "call_delta" in df.columns:
        df["call_delta"] = df["call_delta"].map(lambda x: None if pd.isna(x) else abs(float(x)))

    symbol = _extract_symbol(page_text, url)
    spot = _extract_spot(page_text)
    expiry = _extract_expiry_date(page_text)
    today = dt.datetime.utcnow().date()
    days = (expiry - today).days if expiry else None

    df = df.sort_values(["strike", "call_delta"], kind="mergesort").reset_index(drop=True)
    df["symbol"] = symbol
    df["spot"] = spot
    df["expiry_date"] = expiry.isoformat() if expiry else None
    df["days_to_expiry"] = days
    df["tenor"] = tenor
    df["source_url"] = url

    ordered_cols = OPTIONS_COLUMNS + ["symbol", "spot", "expiry_date", "days_to_expiry", "tenor", "source_url"]
    return df[ordered_cols]


def _render_page_with_playwright(url: str, headless: bool) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required for live options fetch. "
            "Install with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(3_000)
            return page.content()
        finally:
            browser.close()


def _latest_cached_surface(symbol: str, cache_root: Path) -> Optional[pd.DataFrame]:
    sym = symbol.upper()
    if sym == "UNKNOWN":
        return None
    sym_dir = cache_root / sym
    if not sym_dir.exists():
        return None
    for p in sorted(sym_dir.glob("*.parquet"), reverse=True):
        try:
            return pd.read_parquet(p)
        except Exception:
            continue
    for j in sorted(sym_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(j.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else None
            if isinstance(rows, list) and rows:
                return pd.DataFrame(rows)
        except Exception:
            continue
    return None


def _cache_surface(cache_root: Path, symbol: str, html: str, surface: pd.DataFrame, metrics: dict) -> Dict[str, str]:
    stamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M")
    sym_dir = cache_root / symbol.upper()
    sym_dir.mkdir(parents=True, exist_ok=True)

    html_path = sym_dir / f"{stamp}.html"
    parquet_path = sym_dir / f"{stamp}.parquet"
    json_path = sym_dir / f"{stamp}.json"

    html_path.write_text(html, encoding="utf-8")
    try:
        surface.to_parquet(parquet_path, index=False)
    except Exception as exc:
        raise RuntimeError("pyarrow is required for parquet caching. Install with: pip install pyarrow") from exc
    payload = {
        "generated_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "symbol": symbol.upper(),
        "metrics": metrics,
        "rows": surface.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"html": str(html_path), "parquet": str(parquet_path), "json": str(json_path)}


def fetch_options_surface(
    url: str,
    tenor: str = "1M",
    headless: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch and parse an Investing options table, with deterministic local caching."""
    cache_root = Path("out/cache/investing_options")
    cache_root.mkdir(parents=True, exist_ok=True)

    symbol_hint = _guess_symbol_from_url(url) or "UNKNOWN"
    if not refresh:
        cached = _latest_cached_surface(symbol_hint, cache_root)
        if cached is not None and not cached.empty:
            return cached

    html = _render_page_with_playwright(url=url, headless=headless)
    surface = parse_options_surface_html(url=url, html=html, tenor=tenor)
    if surface.empty:
        raise ValueError("Could not parse options table from page HTML")

    symbol = str(surface["symbol"].iloc[0] or symbol_hint).upper()
    metrics = compute_skew_metrics(surface)
    _cache_surface(cache_root=cache_root, symbol=symbol, html=html, surface=surface, metrics=metrics)
    return surface


def _nearest_iv(surface: pd.DataFrame, delta_col: str, target: float) -> Optional[float]:
    if delta_col not in surface.columns or "imp_vol" not in surface.columns:
        return None
    x = surface[[delta_col, "imp_vol"]].copy()
    x[delta_col] = pd.to_numeric(x[delta_col], errors="coerce")
    x["imp_vol"] = pd.to_numeric(x["imp_vol"], errors="coerce")
    x = x.dropna()
    if x.empty:
        return None
    idx = (x[delta_col] - target).abs().idxmin()
    return float(x.loc[idx, "imp_vol"])


def compute_skew_metrics(df: pd.DataFrame) -> dict:
    """Compute options-skew overlay metrics from a parsed options surface."""
    if df is None or df.empty:
        return {
            "label": "NEUTRAL",
            "approx_atm_iv": None,
            "iv_10_put": None,
            "iv_10_call": None,
            "rr10": None,
            "iv_25_put": None,
            "iv_25_call": None,
            "rr25": None,
        }

    x = df.copy()
    for c in ("put_delta", "call_delta", "strike", "imp_vol"):
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")

    atm = _nearest_iv(x, "call_delta", 0.50)
    if atm is None and "strike" in x.columns and "imp_vol" in x.columns:
        y = x[["strike", "imp_vol"]].dropna()
        if not y.empty:
            mid = (float(y["strike"].min()) + float(y["strike"].max())) / 2.0
            idx = (y["strike"] - mid).abs().idxmin()
            atm = float(y.loc[idx, "imp_vol"])

    iv_10_put = _nearest_iv(x, "put_delta", -0.10)
    iv_10_call = _nearest_iv(x, "call_delta", 0.10)
    iv_25_put = _nearest_iv(x, "put_delta", -0.25)
    iv_25_call = _nearest_iv(x, "call_delta", 0.25)

    rr10 = None if (iv_10_put is None or iv_10_call is None) else float(iv_10_call - iv_10_put)
    rr25 = None if (iv_25_put is None or iv_25_call is None) else float(iv_25_call - iv_25_put)

    label = "NEUTRAL"
    if rr10 is not None:
        if rr10 >= 0.40:
            label = "BULLISH"
        elif rr10 <= -0.40:
            label = "BEARISH"

    first = x.iloc[0].to_dict()
    return {
        "symbol": first.get("symbol"),
        "spot": first.get("spot"),
        "expiry_date": first.get("expiry_date"),
        "days_to_expiry": first.get("days_to_expiry"),
        "tenor": first.get("tenor"),
        "label": label,
        "approx_atm_iv": None if atm is None else float(atm),
        "iv_10_put": None if iv_10_put is None else float(iv_10_put),
        "iv_10_call": None if iv_10_call is None else float(iv_10_call),
        "rr10": rr10,
        "iv_25_put": None if iv_25_put is None else float(iv_25_put),
        "iv_25_call": None if iv_25_call is None else float(iv_25_call),
        "rr25": rr25,
    }
