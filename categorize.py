from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"PAYMENT - THANK YOU|PAYMENT THANK YOU|MOBILE PAYMENT|AUTOPAY|ONLINE PAYMENT|MOBILE PMT|DISCOVER DES:E-PAYMENT|DISCOVER E-PAYMENT|AMEX.*PAYMENT|AMERICAN EXPRESS.*PAYMENT|CREDIT CARD PAYMENT|ONLINE BANKING PAYMENT TO CRD"), "Card Payment", "transfer"),
    (re.compile(r"ZELLE|VENMO|CASH APP|CASHAPP|PAYPAL"), "Transfer", "transfer"),
    (re.compile(r"WALMART|TARGET|COSTCO|HEB|KROGER|TRADER JOE|WHOLE FOODS|ALDI|PUBLIX|SAFEWAY"), "Groceries", "expense"),
    (re.compile(r"MCDONALD|CHIPOTLE|STARBUCKS|DOORDASH|UBER ?EATS|GRUBHUB|CHICK-FIL|TACO BELL|SUBWAY|PIZZA|DOMINO|PANERA|WENDY|BURGER KING|CHILI|APPLEBEE|OLIVE GARDEN|IHOP|DENNY"), "Dining", "expense"),
    (re.compile(r"SHELL|EXXON|CHEVRON|VALERO|BP |\bMOBIL\b|CITGO|MARATHON|PILOT|CASEY"), "Gas", "expense"),
    (re.compile(r"\bUBER\b(?! ?EATS)|LYFT|MTA |METRO|TRANSIT|PARKING|TOLL"), "Transit", "expense"),
    (re.compile(r"NETFLIX|SPOTIFY|HULU|DISNEY\+|DISNEY PLUS|APPLE\.COM/BILL|APPLE ONE|HBO|PEACOCK|PARAMOUNT|YOUTUBE PREMIUM|AMAZON PRIME"), "Subscriptions", "expense"),
    (re.compile(r"\bRENT\b|APARTMENT|PROPERTY MGMT|LEASE"), "Rent", "expense"),
    (re.compile(r"AT&T|VERIZON|T-MOBILE|TMOBILE|COMCAST|XFINITY|SPECTRUM|COX |INTERNET|ELECTRIC|GAS CO|WATER BILL|UTILITY"), "Utilities", "expense"),
    (re.compile(r"AMAZON|AMZN MKTP|AMZN\*"), "Shopping", "expense"),
    (re.compile(r"CVS|WALGREEN|PHARMACY|RITE AID|DUANE READE"), "Health & Pharmacy", "expense"),
    (re.compile(r"DOCTOR|CLINIC|HOSPITAL|URGENT CARE|DENTAL|VISION|OPTOMETRIST|HEALTH INS"), "Healthcare", "expense"),
    (re.compile(r"GYM|PLANET FITNESS|24 HOUR|CROSSFIT|YMCA|FITNESS"), "Fitness", "expense"),
    (re.compile(r"ATM WITHDRAWAL|ATM CASH"), "Cash", "expense"),
    (re.compile(r"INTEREST CHARGE|FINANCE CHARGE|LATE FEE|FOREIGN TRANSACTION FEE|ANNUAL FEE|RETURNED ITEM FEE"), "Fees & Interest", "expense"),
    (re.compile(r"PAYROLL|DIRECT DEP|ACH CREDIT.*PAYROLL|SALARY|WAGES"), "Payroll", "income"),
    (re.compile(r"INTEREST PAID|DIVIDEND|SAVINGS INTEREST"), "Interest Income", "income"),
    (re.compile(r"REFUND|CREDIT VOUCHER|RETURN"), "Refund", "income"),
]

_OVERRIDES_PATH = Path(__file__).resolve().parent / "category_overrides.json"


def _load_overrides() -> dict[str, tuple[str, str]]:
    if not _OVERRIDES_PATH.exists():
        return {}
    try:
        raw = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {k: (v["category"], v["type"]) for k, v in raw.items()}
    except Exception:
        return {}


def categorize(item: str, is_debit: bool) -> tuple[str, str]:
    upper = item.upper()
    overrides = _load_overrides()
    for substr, (cat, typ) in overrides.items():
        if substr.upper() in upper:
            return cat, typ
    for pattern, cat, typ in _RULES:
        if pattern.search(upper):
            return cat, typ
    return ("Uncategorized", "expense" if is_debit else "income")


def apply_categorization(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cats, types = [], []
    for _, row in df.iterrows():
        existing_cat = str(row.get("category", "") or "").strip()
        existing_type = str(row.get("type", "") or "").strip()
        item = str(row.get("item", "") or "")
        debits = float(row.get("debits", 0) or 0)

        inferred_cat, inferred_type = categorize(item, debits > 0)

        has_existing_cat = bool(existing_cat and existing_cat.lower() != "nan")
        has_existing_type = bool(existing_type and existing_type.lower() != "nan")

        # Preserve bank-native categories when they are usable, but let explicit
        # transfer/income detection override obviously wrong legacy values.
        if inferred_cat != "Uncategorized" and inferred_type != "expense":
            cats.append(inferred_cat)
            types.append(inferred_type)
            continue

        if has_existing_cat:
            cats.append(existing_cat)
            types.append(existing_type if has_existing_type else ("expense" if debits > 0 else "income"))
            continue

        cats.append(inferred_cat)
        types.append(inferred_type)
    df["category"] = cats
    df["type"] = types
    return df
