# 🏦 Bank Parser — Turn Bank Statements into Spreadsheets

> Upload a bank statement PDF and get back a clean, downloadable CSV in seconds — no accounts, no cloud, no subscriptions. Everything stays on your computer.

---

## 🤔 Why Was This Built?

Dealing with bank statement PDFs is a pain. They're not searchable in a useful way, you can't easily sort or filter transactions, and importing them into Excel or Google Sheets usually requires a lot of manual copy-pasting.

This project was built to solve that problem simply: drop in a PDF, get out a clean spreadsheet.

It was also a hands-on way to learn how to build a local web app with **Python + FastAPI**, work with **PDF text extraction**, and connect a simple front-end to a back-end API — all without relying on any external service.

---

## 💡 What Does It Do?

1. You open the app in your browser (it runs locally on your computer).
2. You drag and drop one or more bank statement PDFs onto the page.
3. The app reads each PDF, finds every transaction line, and pulls out the **date**, **description**, and **amount**.
4. You see a live preview of the data in a table.
5. You download the results as a `.csv` file you can open in Excel, Google Sheets, or any spreadsheet tool.

You can also upload multiple statements at once and **combine them** into a single CSV.

---

## 🏗️ How Was It Built?

The project is split into three layers:

### 1. The Web Server (`app.py`)
Built with **FastAPI**, a modern Python web framework. It handles:
- Serving the web page you see in the browser
- Receiving uploaded PDF files
- Calling the parser and saving results
- Letting you preview and download the generated CSVs

### 2. The PDF Parser (`_bank_parser.py`)
The real workhorse. It uses a library called **pdfplumber** to read raw text out of each PDF page. Then it scans every line looking for ones that start with a date (like `05/12/24`) — those are transaction rows. For each one it grabs:
- **Date** — the first token on the line
- **Amount** — the last token (handles `$`, commas, and parentheses for negatives)
- **Description** — everything in between

The result is a tidy table (called a **DataFrame** in Python) that gets saved as a CSV.

### 3. The Browser UI (`templates/index.html` + `static/app.js`)
A single-page interface built with plain HTML, CSS, and vanilla JavaScript — no fancy frameworks. It gives you:
- A drag-and-drop upload zone
- A live preview table of parsed transactions
- A sidebar listing all previously generated CSVs
- Download and combine buttons

The orange-themed dark design uses glassmorphism effects and smooth animations.

---

## 🔒 Privacy

**Your files never leave your computer.** There is no server in the cloud, no account needed, no data sent anywhere. The app runs entirely on your local machine.

---

## 🚀 How to Run It

You'll need **Python 3.8+** installed. Then open a terminal in this project's folder and run:

```bash
# 1. Create a virtual environment (a clean isolated Python install for this project)
python -m venv .venv

# 2. Activate it
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install the required libraries
pip install -r requirements.txt

# 4. Start the app
uvicorn app:app --reload
```

Then open your browser and go to **http://127.0.0.1:8000**.

That's it! Upload a PDF and you'll see your transactions appear in seconds.

---

## 📁 Project Structure

```
bank-parser-fastapi/
├── app.py              # Web server — handles uploads, files, and routes
├── _bank_parser.py     # PDF parsing logic — finds and extracts transactions
├── templates/
│   └── index.html      # The web page you see in the browser
├── static/
│   ├── app.js          # Front-end logic (drag-and-drop, previews, downloads)
│   └── styles.css      # Orange-themed dark UI styling
├── requirements.txt    # Python libraries this project needs
├── .uploads/           # Where uploaded PDFs are temporarily stored (not in git)
└── .outputs/           # Where generated CSV files are saved (not in git)
```

---

## 🛠️ Key Libraries Used

| Library | What it does |
|---|---|
| `fastapi` | Web framework — handles HTTP routes and requests |
| `uvicorn` | Runs the FastAPI app as a local web server |
| `pdfplumber` | Extracts text from PDF files |
| `pandas` | Organizes transaction data into tables and exports to CSV |
| `jinja2` | Fills in the HTML template with dynamic data |
| `python-multipart` | Allows FastAPI to receive uploaded files |

---

## ⚠️ Notes

- The parser works best on **text-based PDFs** (standard e-statements). Scanned image PDFs won't work since there's no readable text inside them.
- Parsing errors on individual files are shown in the UI and won't crash the whole session.
- Generated CSVs stay in `.outputs/` until you click "Clear All" or delete them manually.

