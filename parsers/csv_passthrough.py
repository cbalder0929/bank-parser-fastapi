from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import CANONICAL_COLUMNS, clean_description, empty_canonical, normalize_date, to_canonical

# Column maps: (debit_col, credit_col, date_col, desc_col, amount_col, signed)
# signed=True means a single amount column where negative = credit
_DISCOVER_COLS = {
    "date": "Trans. Date",
    "desc": "Description",
    "amount": "Amount",
    "signed": True,
    "category_col": "Category",
}
_AMEX_COLS = {
    "date": "Date",
    "desc": "Description",
    "amount": "Amount",
    "signed": True,
    "category_col": "Category",
}
_BOA_CHECKING_COLS = {
    "date": "Date",
    "desc": "Description",
    "amount": "Amount",
    "signed": True,
}
_BOA_CREDIT_COLS = {
    "date": "Posted Date",
    "desc": "Payee",
    "amount": "Amount",
    "signed": True,
}

_SOURCE_MAP = {
    "discover": ("discover", "Discover Card", _DISCOVER_COLS),
    "amex": ("amex", "American Express", _AMEX_COLS),
    "boa_checking": ("boa_checking", "BoA Checking", _BOA_CHECKING_COLS),
    "boa_credit": ("boa_credit", "BoA Credit Card", _BOA_CREDIT_COLS),
}


def parse(path: Path, source: str) -> pd.DataFrame:
    cfg = _SOURCE_MAP.get(source)
    if cfg is None:
        return empty_canonical()

    source_slug, account_label, col_map = cfg

    try:
        raw = pd.read_csv(path)
    except Exception:
        return empty_canonical()

    rows: list[dict] = []
    date_col = col_map["date"]
    desc_col = col_map["desc"]
    amount_col = col_map.get("amount")
    category_col = col_map.get("category_col")

    for _, r in raw.iterrows():
        try:
            date_raw = str(r.get(date_col, "") or "").strip()
            date = normalize_date(date_raw)
            if not date or date == date_raw:
                # Try pandas parse as fallback
                try:
                    import pandas as _pd
                    date = _pd.to_datetime(date_raw).strftime("%Y-%m-%d")
                except Exception:
                    continue

            item = clean_description(str(r.get(desc_col, "") or ""))
            raw_amount = float(str(r.get(amount_col, 0) or 0).replace(",", "").replace("$", ""))

            # For signed column: negative = payment/credit, positive = charge/debit
            if raw_amount < 0:
                debits, credits = 0.0, abs(raw_amount)
            else:
                debits, credits = raw_amount, 0.0

            category = str(r.get(category_col, "") or "") if category_col else None

            rows.append({
                "date": date,
                "debits": debits,
                "credits": credits,
                "category": category or None,
                "item": item,
                "type": None,
                "source": None,
                "account": None,
            })
        except (ValueError, TypeError):
            continue

    if not rows:
        return empty_canonical()
    df = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    return to_canonical(df, source_slug, account_label)
