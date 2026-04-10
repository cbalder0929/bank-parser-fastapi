
​Balderas, Charles​
# Bank Parser – Project Guide

 

> **What it does:** A local web app that converts bank statement PDFs into clean, downloadable CSV files.

 

---

 

## Architecture Overview

 

```

┌─────────────────────────────────────────────────────┐

│                    Browser (UI)                     │

│  templates/index.html  +  static/app.js + styles    │

└────────────┬───────────────────────────┬────────────┘

             │  POST /api/parse          │  GET /api/files, preview, download

             ▼                           ▼

┌─────────────────────────────────────────────────────┐

│              FastAPI Server  (app.py)                │

│  • Serves the HTML page at GET /                    │

│  • Accepts PDF uploads via POST /api/parse          │

│  • Lists, previews, and downloads generated CSVs    │

└────────────┬────────────────────────────────────────┘

             │  calls parse_pdf_to_df()

             ▼

┌─────────────────────────────────────────────────────┐

│         PDF Parser  (_bank_parser.py)                │

│  • Opens each PDF with pdfplumber                   │

│  • Finds transaction lines matching MM/DD/YY dates  │

│  • Extracts Date, Description, Amount into a        │

│    pandas DataFrame                                 │

└─────────────────────────────────────────────────────┘

```

 

---

 

## File-by-File Breakdown

 

### `app.py` – FastAPI Server (the brain)

 

The main entry point. Run with `uvicorn app:app --reload`.

 

| Route | Method | Purpose |

|---|---|---|

| `/` | GET | Renders the HTML UI via Jinja2 (`templates/index.html`) |

| `/api/parse` | POST | Accepts one or more PDF uploads, parses each through `_bank_parser.py`, saves the resulting CSV to `.outputs/`, and returns metadata (id, name, row count, columns) |

| `/api/files` | GET | Lists all generated CSVs in `.outputs/`, sorted newest-first |

| `/api/files/{file_id}/preview` | GET | Reads a CSV back into pandas and returns up to N rows as JSON for the preview table |

| `/api/files/{file_id}/download` | GET | Streams the CSV file as a download |

 

**Key details:**

- Uploaded PDFs are saved to `.uploads/` with a random token to avoid collisions.

- Output CSVs are named `<token>__<original_name>.csv` so the ID and display name can be split apart.

- Static files (JS, CSS, images) are served from `/static/`.

 

### `_bank_parser.py` – PDF Parsing Logic

 

The core parsing engine. It has **one main function**:

 

```python

def parse_pdf_to_df(pdf_path) -> pd.DataFrame:

```

 

**How it works:**

1. Opens the PDF with `pdfplumber`.

2. Extracts raw text from every page.

3. Scans each line for a date pattern (`MM/DD/YY`) at the start — these are transaction rows.

4. Splits each matching line into: **Date** (first token), **Amount** (last token), **Description** (everything in between).

5. Cleans the amount string (removes `$`, commas, handles parenthesized negatives like `(12.00)` → `-12.00`).

6. Returns a DataFrame with columns: `Date`, `Description`, `Amount`.

 

Lines that don't start with a date or have malformed amounts are silently skipped.

 

### `templates/index.html` – The UI Layout

 

A single-page Jinja2 template with three main sections:

 

1. **Upload Panel** – Drag-and-drop zone, file/folder browser buttons, and a "Parse to CSV" button.

2. **CSV Preview** – Shows the parsed data in a table with column headers and row data.

3. **Generated CSVs Sidebar** – Lists all previously generated CSVs; click one to preview it.

 

### `static/app.js` – Frontend Logic

 

Handles all client-side interactivity (no framework, vanilla JS):

 

- **File selection** – Drag-and-drop, file picker, or folder picker. Files are de-duped by name+size+lastModified.

- **Upload flow** – Sends all selected PDFs as a single `FormData` POST to `/api/parse`, then auto-selects the first result for preview.

- **Output list** – Fetches `/api/files` and renders clickable cards.

- **Preview** – Fetches `/api/files/{id}/preview` and builds the HTML table dynamically.

- **Download** – Navigates to `/api/files/{id}/download` to trigger a browser download.

 

### `static/styles.css` – Styling

 

Orange-themed dark UI with glassmorphism effects, gradients, and smooth animations.

 

### `requirements.txt` – Python Dependencies

 

Key packages:

- **`fastapi`** + **`uvicorn`** – Web server

- **`pdfplumber`** – PDF text extraction

- **`pandas`** – DataFrame handling and CSV generation

- **`jinja2`** – HTML templating

- **`python-multipart`** – Required for FastAPI file uploads

 

---

 

## Data Flow (step by step)

 

```

1. User drops PDF(s) in the browser

2. Browser collects File objects, shows them in the selected list

3. User clicks "Parse to CSV"

4. app.js POSTs files to /api/parse

5. app.py saves each PDF to .uploads/

6. app.py calls _bank_parser.parse_pdf_to_df() on each PDF

7. _bank_parser opens the PDF, scans for date-prefixed lines, extracts transactions

8. app.py writes the DataFrame to a CSV in .outputs/

9. app.py responds with JSON: { created: [...], errors: [...] }

10. app.js auto-loads the preview for the first created CSV

11. User can download the CSV or preview other files

```

 

---

 

## Running Locally

 

```bash

# 1. Create and activate a virtual environment

python -m venv .venv

.\.venv\Scripts\activate        # Windows

# source .venv/bin/activate     # macOS/Linux

 

# 2. Install dependencies

pip install -r requirements.txt

 

# 3. Start the dev server

uvicorn app:app --reload

```

 

Then open **http://127.0.0.1:8000** in your browser.

 

---

 

## Important Directories

 

| Path | Purpose | Git-tracked? |

|---|---|---|

| `.uploads/` | Temporary storage for uploaded PDFs | ❌ (gitignored) |

| `.outputs/` | Generated CSV files | ❌ (gitignored) |

| `static/` | JS, CSS, and image assets | ✅ |

| `templates/` | Jinja2 HTML templates | ✅ |

 

---

 

## Conventions & Notes

 

- **Privacy-first:** All processing is local. PDFs never leave the machine.

- **Error handling:** Parsing errors are returned per-file in the API response; they don't crash the server or block other files.

- **File naming:** Output CSVs use `<token>__<name>.csv` format. Legacy `<token>_<name>.csv` format is also supported for backwards compatibility.

- **No database:** Everything is file-based. CSVs persist in `.outputs/` until manually deleted.

 

 