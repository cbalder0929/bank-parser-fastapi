"""Backwards-compatibility shim. New code should use parsers.parse() directly."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from parsers import parse as _parse


def parse_pdf_to_df(pdf_path: str | Path) -> pd.DataFrame:
    """Return canonical-schema DataFrame for the given PDF."""
    return _parse(Path(pdf_path))


def parse_pdf_to_csv_bytes(pdf_path: str | Path) -> bytes:
    df = parse_pdf_to_df(pdf_path)
    return df.to_csv(index=False).encode("utf-8")
