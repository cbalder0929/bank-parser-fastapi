# Bank Parser (PDF → CSV)

Orange-themed local web tool that uploads bank statement PDFs, parses transactions, previews the resulting CSV, and lets you download it.

## Run

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Then open `http://127.0.0.1:8000`.

## Notes

- The parsing logic lives in `_bank_parser.py` (`parse_pdf_to_df`).
- Uploaded PDFs are saved to `.uploads/` and generated CSVs to `.outputs/`.

