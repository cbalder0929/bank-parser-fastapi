
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber


# Matches transaction lines that start with MM/DD/YY (checking/savings) or
# MM/DD (credit card) date formats.
DATE_RE = re.compile(r"^\d{2}/\d{2}(?:/\d{2})?\b")

# Individual date-token patterns used to detect the dual-date credit card format.
_DATE_TOKEN_RE = re.compile(r"^\d{2}/\d{2}(?:/\d{2})?$")

# Line-level noise keywords that indicate summary/header rows — not transactions.
_NOISE_KEYWORDS = (
    "TOTAL",
    "ACCOUNT SUMMARY",
    "PAGE",
    "BALANCE",
    "STATEMENT",
    "CONTINUED",
)


def _is_date_token(token: str) -> bool:
    """Return True if *token* looks like a date (MM/DD/YY or MM/DD)."""
    return bool(_DATE_TOKEN_RE.match(token))


def _clean_amount(value: str) -> float:
    # Normalize "$1,234.56", "-$123.45", and "(12.00)" into numeric values.
    raw = value.strip()
    # Preserve a leading minus sign before stripping the dollar sign.
    negative = raw.startswith("-")
    raw = (raw[1:] if negative else raw).replace("$", "").replace(",", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
        negative = True
    result = float(raw)
    return -result if negative else result


def parse_pdf_to_df(pdf_path: str | Path) -> pd.DataFrame:
    # Main parser result: one dict per transaction row found in the PDF text.
    pdf_path = Path(pdf_path)
    transactions: list[dict[str, object]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                # Skip lines that are not transaction rows.
                if not DATE_RE.match(line):
                    continue

                # Skip header/summary noise lines (case-insensitive).
                line_upper = line.upper()
                if any(kw in line_upper for kw in _NOISE_KEYWORDS):
                    continue

                parts = line.split()
                if len(parts) < 3:
                    continue

                date = parts[0]

                # Credit card lines have a second date token (posting date)
                # right after the transaction date.  When detected, skip that
                # token so the description starts at parts[2] instead of parts[1].
                # parts[1] is safe to access here because len(parts) >= 3 above.
                if _is_date_token(parts[1]):
                    # parts[0] = transaction date, parts[1] = posting date (ignored)
                    desc_start = 2
                else:
                    # Standard checking/savings format: description starts at parts[1]
                    desc_start = 1

                if len(parts) < desc_start + 2:
                    # Need at least one description token and one amount token.
                    continue

                amount_raw = parts[-1]
                description = " ".join(parts[desc_start:-1]).strip()

                try:
                    amount = _clean_amount(amount_raw)
                except ValueError:
                    # Ignore malformed rows instead of failing the full file.
                    continue

                transactions.append(
                    {
                        "Date": date,
                        "Description": description,
                        "Amount": amount,
                    }
                )

    return pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])


def parse_pdf_to_csv_bytes(pdf_path: str | Path) -> bytes:
    # Convenience helper for HTTP/file download cases.
    df = parse_pdf_to_df(pdf_path)
    return df.to_csv(index=False).encode("utf-8")


if __name__ == "__main__":
    # Simple local test run (kept for convenience).
    in_pdf = Path("bankStates/eStmt08.pdf")
    out_csv = Path("clean_statement.csv")

    df = parse_pdf_to_df(in_pdf)
    print(df)
    out_csv.write_bytes(df.to_csv(index=False).encode("utf-8"))
    print(f"CSV exported successfully to {out_csv}")
