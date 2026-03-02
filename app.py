from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from _bank_parser import parse_pdf_to_df


# Project root used to build stable absolute paths.
ROOT = Path(__file__).resolve().parent
# Temporary storage for uploaded PDFs before parsing.
UPLOADS_DIR = ROOT / ".uploads"
# Output storage for generated CSV files.
OUTPUT_DIR = ROOT / ".outputs"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def _safe_stem(name: str) -> str:
    # Keep output filenames readable but safe for the filesystem.
    stem = Path(name).stem.strip() or "statement"
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return stem[:80] or "statement"


def _now_ms() -> int:
    return int(time.time() * 1000)


# FastAPI app object that owns routes/middleware.
app = FastAPI()
# Jinja environment for rendering server-side HTML.
templates = Jinja2Templates(directory=str(ROOT / "templates"))

app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    # Main UI page.
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/parse")
async def parse(files: list[UploadFile] = File(...)) -> JSONResponse:
    # Metadata returned for successfully parsed files.
    created: list[dict[str, Any]] = []
    # Per-file errors returned to the UI.
    errors: list[dict[str, Any]] = []

    for f in files:
        filename = f.filename or "statement.pdf"
        if not filename.lower().endswith(".pdf"):
            errors.append({"file": filename, "error": "Only PDF files are supported."})
            continue

        token = secrets.token_urlsafe(10)
        # Unique upload/output names avoid collisions for same input filename.
        safe_base = _safe_stem(filename)
        upload_path = UPLOADS_DIR / f"{safe_base}_{token}.pdf"
        out_id = token
        out_name = f"{safe_base}.csv"
        out_path = OUTPUT_DIR / f"{out_id}__{out_name}"

        try:
            content = await f.read()
            upload_path.write_bytes(content)

            df = parse_pdf_to_df(upload_path)
            out_path.write_text(df.to_csv(index=False), encoding="utf-8", newline="")

            created.append(
                {
                    "id": out_id,
                    "name": out_name,
                    "rows": int(df.shape[0]),
                    "columns": list(df.columns),
                }
            )
        except Exception as e:  # noqa: BLE001 - surface error in UI
            errors.append({"file": filename, "error": str(e)})
            try:
                if out_path.exists():
                    out_path.unlink()
            except Exception:
                pass
        finally:
            try:
                await f.close()
            except Exception:
                pass

    return JSONResponse({"created": created, "errors": errors})


@app.get("/api/files")
def list_files() -> JSONResponse:
    # Ordered newest-first so users see recent parses first.
    items: list[dict[str, Any]] = []
    for p in sorted(OUTPUT_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        # stored as "<id>__<name>.csv" (legacy: "<id>_<name>.csv")
        if "__" in p.name:
            file_id, rest = p.name.split("__", 1)
        else:
            try:
                file_id, rest = p.name.split("_", 1)
            except ValueError:
                file_id, rest = p.stem, p.name
        items.append({"id": file_id, "filename": rest, "size": p.stat().st_size})

    return JSONResponse({"files": items})


@app.get("/api/files/{file_id}/preview")
def preview(file_id: str, limit: int = 50) -> JSONResponse:
    # Support both current "__" and legacy "_" output filename formats.
    matches = list(OUTPUT_DIR.glob(f"{file_id}__*.csv")) or list(OUTPUT_DIR.glob(f"{file_id}_*.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail="CSV not found")

    path = matches[0]
    df = parse_csv_for_preview(path, limit=limit)
    display_name = path.name.split("__", 1)[1] if "__" in path.name else path.name.split("_", 1)[1]
    return JSONResponse(
        {
            "filename": display_name,
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
        }
    )


def parse_csv_for_preview(path: Path, limit: int) -> "pd.DataFrame":
    import pandas as pd

    # Clamp preview rows to keep UI responsive and avoid huge payloads.
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    return pd.read_csv(path).head(limit)


@app.get("/api/files/{file_id}/download")
def download(file_id: str) -> FileResponse:
    # Support both current "__" and legacy "_" output filename formats.
    matches = list(OUTPUT_DIR.glob(f"{file_id}__*.csv")) or list(OUTPUT_DIR.glob(f"{file_id}_*.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail="CSV not found")

    path = matches[0]
    download_name = path.name.split("__", 1)[1] if "__" in path.name else path.name.split("_", 1)[1]
    return FileResponse(
        path,
        media_type="text/csv",
        filename=download_name,
    )

