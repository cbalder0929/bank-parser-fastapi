from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

CANONICAL_COLUMNS = ["date", "debits", "credits", "category", "item", "type", "source", "account"]


def clean_amount(value: str) -> float:
    raw = value.strip()
    negative = raw.startswith("-")
    if raw.upper().endswith("CR"):
        raw = raw[:-2].strip()
        negative = False
    raw = (raw[1:] if raw.startswith("-") else raw).replace("$", "").replace(",", "").strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
        negative = True
    result = float(raw)
    return -result if negative else result


def normalize_date(raw: str, statement_year: int | None = None) -> str:
    raw = raw.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    if re.match(r"^\d{2}/\d{2}$", raw):
        year = statement_year or datetime.now().year
        try:
            return datetime.strptime(f"{raw}/{year}", "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return raw


def clean_description(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def extract_year(text: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", text[:3000])
    return int(m.group(1)) if m else None


def to_canonical(df: pd.DataFrame, source: str, account: str) -> pd.DataFrame:
    df = df.copy()
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["source"] = source
    df["account"] = account
    return df[CANONICAL_COLUMNS]


def empty_canonical() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)
