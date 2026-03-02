
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber


# Matches transaction lines that start with a date like "08/21/25".
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}\b")


def _clean_amount(value: str) -> float:
    # Normalize "$1,234.56" and "(12.00)" into numeric values.
    raw = value.strip()
    raw = raw.replace("$", "").replace(",", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = f"-{raw[1:-1]}"
    return float(raw)


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

                parts = line.split()
                if len(parts) < 3:
                    continue

                date = parts[0]
                amount_raw = parts[-1]
                description = " ".join(parts[1:-1]).strip()

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
