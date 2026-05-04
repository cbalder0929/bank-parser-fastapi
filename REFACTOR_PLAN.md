# Refactor Plan: From Raw Parser → Financial Insight Tool

This document is the implementation plan for turning Bank Parser from a "PDF → flat CSV" tool into a tool that **understands** the data: where money came in, where it went, and what categories it falls into. End goal: a **Generate Reports** button in the header that opens a new tab with charts and tables summarizing income, spending, and balances across all uploaded statements.

Audience: AI assistants and human contributors picking up the work. Read top to bottom — phases build on each other.

---

## 1. Goals (what "done" looks like)

1. Support all four sources the user actually uses:
   - **Discover** (credit card)
   - **American Express / Amex** (credit card)
   - **Bank of America Checking** (debit account)
   - **Bank of America Credit Card**
   - Both PDF statements and CSV exports for each.
2. A **single canonical schema** every parsed file is normalized into:
   ```
   date, debits, credits, category, item, type, source, account
   ```
3. Automatic **categorization** (groceries, dining, gas, rent, payroll, transfers, etc.) and **type classification** (asset / liability / income / expense / transfer).
4. A **Generate Reports** button in the header that opens `/reports` in a new tab and shows:
   - Total income vs. total spending for the selected period
   - Income breakdown by source (employer, refunds, transfers in, etc.)
   - Spending breakdown by category (pie/donut)
   - Spending over time (line/bar by month)
   - Top merchants / items
   - Net cash flow per account
5. Everything stays **local** (no third-party APIs, no cloud).

---

## 2. Canonical Output Schema

Every parser, regardless of source, must emit rows in this exact shape:

| Column | Type | Description |
|---|---|---|
| `date` | ISO date `YYYY-MM-DD` | Transaction post date |
| `debits` | float (≥ 0) | Money **out** of user's pocket (purchases, fees, withdrawals). Empty/0 if not a debit. |
| `credits` | float (≥ 0) | Money **in** to user's pocket (deposits, payroll, refunds, payments to credit card). Empty/0 if not a credit. |
| `category` | string | Normalized category label (see §4). Examples: `Groceries`, `Dining`, `Gas`, `Payroll`, `Transfer`, `Uncategorized`. |
| `item` | string | Cleaned merchant/description (no statement noise). |
| `type` | enum | `asset` \| `liability` \| `income` \| `expense` \| `transfer` (see §5). |
| `source` | enum | `discover` \| `amex` \| `boa_checking` \| `boa_credit` (slug per institution+account). |
| `account` | string | User-friendly account label (e.g. "BoA Checking ••1234"). |

**Why split debits/credits instead of signed `amount`:** matches accounting conventions, simpler for sums in the report layer, and avoids sign-confusion bugs across credit-card statements (where a "charge" is positive on the bill but a debit to the cardholder).

Keep the legacy `Date,Description,Amount` CSVs working through a **migration helper** so old outputs in `.outputs/` still preview.

---

## 3. Per-Source Parsing — What to Fix

Current `_bank_parser.py` is a single regex-based parser that only handles BoA-shaped lines. Replace it with a **dispatcher** that detects the source and routes to a dedicated parser.

### 3.1 Detection
Add `detect_source(text_or_df) -> SourceSlug`. Heuristics:

- Search the first ~2 pages of PDF text or first column-headers of CSV for institution markers:
  - `discover.com`, `Discover Card` → `discover`
  - `americanexpress.com`, `Membership Rewards` → `amex`
  - `Bank of America` + `Checking` → `boa_checking`
  - `Bank of America` + `Credit Card` / `cash rewards` → `boa_credit`
- Fallback: ask user to pick from a dropdown if detection is ambiguous.

### 3.2 Source-specific parsers

Create `parsers/` package, one file per source:

```
parsers/
  __init__.py          # exposes parse(path, source) and detect_source()
  base.py              # shared helpers: clean_amount, normalize_date, etc.
  discover.py
  amex.py
  boa_checking.py
  boa_credit.py
  csv_passthrough.py   # for native CSV exports — column-mapping per source
```

Each parser exports `parse(path: Path) -> pd.DataFrame` returning the **canonical schema**. PDF parsers continue to use `pdfplumber`. CSV parsers use `pandas.read_csv` plus a column-rename map.

Known per-source quirks to handle:

- **Discover PDF:** dual `Trans Date / Post Date` columns, payments shown as negative on statement; payments must become `credits`, purchases become `debits`. Interest charges → `expense`.
- **Amex PDF:** "New Charges" section per cardmember; foreign transactions show currency conversion lines that must be skipped. Payments to Amex → `credits` and `transfer` (from the cardholder's checking) — keep them as `credit` rows on the Amex side, the matching debit lives on the checking side.
- **BoA Checking PDF:** withdrawals/deposits are in separate sections per page; current parser conflates them. Use section headers (`Deposits and other additions`, `Withdrawals and other subtractions`, `Service fees`) to assign debit/credit cleanly.
- **BoA Credit PDF:** similar to Discover. "Payment - Thank You" rows are credits (transfer in from checking).
- **CSV passthrough:** detect the export format and rename columns; do NOT try to re-parse the file. Each bank's CSV export uses different headers — keep a small map per source.

### 3.3 Cleanups in shared base
Move into `parsers/base.py`:
- `clean_amount` (already present, generalize for `1,234.56`, `(12.00)`, `-$5.00`, trailing `CR`).
- `normalize_date(raw, statement_year)` — credit cards omit the year; pass the statement's year (extracted from PDF metadata or filename).
- `clean_description(raw)` — strip trailing reference numbers, city/state codes, repeated whitespace.

---

## 4. Categorization Engine

New module `categorize.py`. Pure-Python, no ML, no external API.

### 4.1 Approach
- A list of `(regex, category, type)` rules ordered by specificity.
- Match against the cleaned `item` string (uppercase).
- First match wins; everything unmatched falls back to `("Uncategorized", "expense" or "income" depending on debit/credit)`.

### 4.2 Initial rule set (seed — extend over time)

| Pattern | Category | Type |
|---|---|---|
| `WALMART\|TARGET\|COSTCO\|HEB\|KROGER\|TRADER JOE` | Groceries | expense |
| `MCDONALD\|CHIPOTLE\|STARBUCKS\|DOORDASH\|UBER ?EATS\|GRUBHUB` | Dining | expense |
| `SHELL\|EXXON\|CHEVRON\|VALERO\|BP ` | Gas | expense |
| `UBER\b\|LYFT\|MTA\|METRO` | Transit | expense |
| `NETFLIX\|SPOTIFY\|HULU\|DISNEY\+\|APPLE\.COM/BILL` | Subscriptions | expense |
| `RENT\|APARTMENT\|PROPERTY MGMT` | Rent | expense |
| `AT&T\|VERIZON\|T-MOBILE\|COMCAST\|XFINITY` | Utilities | expense |
| `AMAZON\|AMZN MKTP` | Shopping | expense |
| `PAYROLL\|DIRECT DEP\|ACH CREDIT.*PAYROLL` | Payroll | income |
| `INTEREST PAID\|DIVIDEND` | Interest Income | income |
| `REFUND\|CREDIT VOUCHER` | Refund | income |
| `PAYMENT - THANK YOU\|MOBILE PAYMENT\|AUTOPAY` | Card Payment | transfer |
| `ZELLE\|VENMO\|CASH APP` (credit) | Transfer In | transfer |
| `ZELLE\|VENMO\|CASH APP` (debit) | Transfer Out | transfer |
| `ATM WITHDRAWAL` | Cash | expense |
| `INTEREST CHARGE\|FINANCE CHARGE\|LATE FEE\|FOREIGN TRANSACTION FEE` | Fees & Interest | expense |

Store these in `categorize.py` as a Python list (NOT a JSON config) so adding rules is one PR.

### 4.3 User overrides (later phase)
Add a `category_overrides.json` keyed by `item` substring → `(category, type)`. The categorizer checks overrides before the regex list. UI for managing overrides is **out of scope** for v1; editing the JSON file is fine.

---

## 5. Type Classification

`type` is derived from category + which side (debit/credit) the row sits on:

| Situation | type |
|---|---|
| Credit on a checking/savings (deposit, payroll, refund, interest paid) | `income` (or `transfer` if it's a card payment received, etc.) |
| Debit on a checking/savings (purchase, fee, withdrawal) | `expense` |
| Charge on a credit card | `expense` (it adds to liability — the report layer will handle the asset/liability rollup) |
| Credit-card payment (debit on checking, credit on card) | `transfer` on both sides |
| Opening/closing balances | not stored as transactions |

`asset` and `liability` are **account-level**, not row-level. Treat them as account metadata:
- `boa_checking` → asset
- `discover`, `amex`, `boa_credit` → liability

The reports layer combines per-row `type` with account-level asset/liability to compute net worth deltas.

---

## 6. Report Generation

### 6.1 Backend: new endpoints in `app.py`

```
GET  /reports                 → renders templates/reports.html
GET  /api/reports/summary     → JSON: totals, period, account breakdown
GET  /api/reports/by-category → JSON: [{category, debit_total, credit_total, count}]
GET  /api/reports/by-month    → JSON: [{month, income, spending, net}]
GET  /api/reports/top-items   → JSON: [{item, total, count}]
```

All report endpoints read every CSV in `.outputs/`, concatenate, and aggregate in pandas. Query params:
- `from=YYYY-MM-DD`, `to=YYYY-MM-DD` for date range
- `accounts=boa_checking,discover` for source filter

### 6.2 Frontend: new page

- New file: `templates/reports.html`
- New file: `static/reports.js`
- New file: `static/reports.css` (or extend `styles.css`)
- Use **Chart.js** (single CDN `<script>` tag — no npm/build step). It's the lightest charting lib that gives donut + line + bar without ceremony. Pin to a specific version.
- Layout:
  - Top: date range picker + account filter chips
  - KPI strip: Total Income, Total Spending, Net, Top Category
  - Row 1: Spending by Category (donut), Income by Source (donut)
  - Row 2: Monthly Income vs Spending (grouped bar, last 12 months)
  - Row 3: Top Merchants (table, top 20 by spend)
  - Row 4: Recent transactions table (paginated, with category labels)

### 6.3 Header button

In `templates/index.html`, in the existing `topbar-actions` div, add:

```html
<a class="primary" href="/reports" target="_blank" rel="noopener">Generate Reports</a>
```

Style it as a primary CTA in `styles.css` so it stands out from the existing "Docs" ghost link.

---

## 7. Migration & Backwards Compatibility

- Keep reading legacy `Date,Description,Amount` CSVs. Add `migrate_legacy_df(df, source_hint) -> df` that maps old columns to new schema. Run it lazily on read in the reports layer, NOT by rewriting files on disk.
- The `/api/files/{id}/preview` endpoint should display whichever schema the file actually has.
- Old `<token>__<name>.csv` filename convention stays.

---

## 8. Concrete Implementation Order (do these in sequence)

Each step is a self-contained PR-sized chunk.

1. **Add canonical schema constants** — `parsers/base.py` with `CANONICAL_COLUMNS = [...]` and a `to_canonical(df, source, account)` helper.
2. **Extract current BoA logic** into `parsers/boa_checking.py` and `parsers/boa_credit.py`, each emitting canonical schema. Old `_bank_parser.py` becomes a thin shim that calls `parsers.parse(path)`.
3. **Add detection + dispatcher** in `parsers/__init__.py`. Update `app.py` `/api/parse` to call it.
4. **Add Discover and Amex parsers**. Test against real sample PDFs (use `.uploads/` test fixtures, gitignored).
5. **Add CSV passthrough parsers** for each bank's native CSV export.
6. **Add `categorize.py`** with the rule list. Apply during parse so `category` and `type` are filled before writing the output CSV.
7. **Build report endpoints** (`/api/reports/...`). No UI yet — verify with curl/browser.
8. **Build `/reports` page**: HTML + Chart.js + reports.js. Wire each chart to its endpoint.
9. **Add header button** linking to `/reports`.
10. **Polish:** loading states, empty-state when no data, date-range UX, account chips.
11. **(Optional)** category override UI.

Stop and test after each step. After steps 6 and 9 specifically, do a full manual smoke test with at least one statement from each of the four sources.

---

## 9. Files to Add / Modify

**New:**
- `parsers/__init__.py`
- `parsers/base.py`
- `parsers/discover.py`
- `parsers/amex.py`
- `parsers/boa_checking.py`
- `parsers/boa_credit.py`
- `parsers/csv_passthrough.py`
- `categorize.py`
- `reports.py` (or extend `app.py` — keep one file unless it grows past ~400 lines)
- `templates/reports.html`
- `static/reports.js`

**Modify:**
- `_bank_parser.py` → shim for backwards compat, or delete and update imports.
- `app.py` → wire dispatcher, add report endpoints, add `/reports` route.
- `templates/index.html` → add "Generate Reports" header button.
- `static/styles.css` → primary-button style for header CTA + `/reports` styles (or split).
- `requirements.txt` → no changes expected (Chart.js is CDN, pandas already present).
- `CLAUDE.md` → update architecture diagram and file breakdown after this lands.

**Delete:** nothing yet — once the dispatcher is stable, the `_bank_parser.py` shim can go.

---

## 10. Open Questions (decide before/during implementation)

1. **Statement year for credit cards:** extract from PDF metadata, or require it in the filename? Default plan: parse the "Statement Closing Date" line from the PDF; fall back to file mtime year.
2. **Duplicate transactions across statements** (overlapping date ranges): dedupe on `(date, source, item, debits, credits)` in the reports layer.
3. **Multi-currency** (Amex foreign txns): out of scope for v1 — convert to USD using the bank's stated rate already on the line, drop the FX info row.
4. **Persistence of categorized data:** rewriting CSVs every time rules change is wasteful. v1: keep raw rows in CSV, run categorization fresh on each report load. Cache later if it gets slow.

---

## 11. Non-Goals (explicitly out of scope)

- Multi-user support / accounts / login
- Cloud sync, mobile app, browser extension
- Tax reporting / 1099 generation
- Forecasting, budgets with alerts
- ML-based categorization
- Editing transactions in the UI

Keep the surface small. Ship the four parsers + reports page first; everything else is a follow-up.
