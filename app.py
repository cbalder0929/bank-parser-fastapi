from __future__ import annotations

import secrets
import time
from io import StringIO
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from categorize import apply_categorization
from parsers import detect_source, parse as parse_file

ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = ROOT / ".uploads"
OUTPUT_DIR = ROOT / ".outputs"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def _safe_stem(name: str) -> str:
    stem = Path(name).stem.strip() or "statement"
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return stem[:80] or "statement"


def _now_ms() -> int:
    return int(time.time() * 1000)


app = FastAPI()
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


# ---------------------------------------------------------------------------
# Legacy migration helper
# ---------------------------------------------------------------------------

def migrate_legacy_df(df: pd.DataFrame) -> pd.DataFrame:
    """Map old Date/Description/Amount columns to canonical schema."""
    if "date" in df.columns:
        return df
    new = pd.DataFrame()
    new["date"] = pd.to_datetime(df.get("Date", pd.Series(dtype=str)), errors="coerce").dt.strftime("%Y-%m-%d")
    new["item"] = df.get("Description", pd.Series(dtype=str))
    amounts = pd.to_numeric(df.get("Amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    new["debits"] = amounts.where(amounts < 0, 0).abs()
    new["credits"] = amounts.where(amounts >= 0, 0)
    new["category"] = None
    new["type"] = None
    new["source"] = "unknown"
    new["account"] = "Unknown"
    return new


def _load_all_outputs() -> pd.DataFrame:
    frames = []
    for p in OUTPUT_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(p)
            if "date" not in df.columns:
                df = migrate_legacy_df(df)
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return _prepare_reports_df(combined)


def _prepare_reports_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared.get("date"), errors="coerce")
    prepared["debits"] = pd.to_numeric(prepared.get("debits", 0), errors="coerce").fillna(0)
    prepared["credits"] = pd.to_numeric(prepared.get("credits", 0), errors="coerce").fillna(0)
    prepared["item"] = prepared.get("item", pd.Series(dtype=str)).fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    prepared["source"] = prepared.get("source", pd.Series(dtype=str)).fillna("unknown").astype(str)
    prepared["category"] = prepared.get("category", pd.Series(dtype=str))
    prepared["type"] = prepared.get("type", pd.Series(dtype=str))

    prepared = apply_categorization(prepared)

    dedupe_subset = ["date", "source", "item", "debits", "credits"]
    prepared = prepared.assign(
        debits=prepared["debits"].round(2),
        credits=prepared["credits"].round(2),
    ).drop_duplicates(subset=dedupe_subset, keep="first")

    return prepared


def _cashflow_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "type" not in df.columns:
        return df
    return df[df["type"] != "transfer"].copy()


def _filter_df(
    df: pd.DataFrame,
    from_date: str | None,
    to_date: str | None,
    accounts: str | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    if from_date and isinstance(from_date, str):
        try:
            df = df[df["date"] >= pd.to_datetime(from_date)]
        except Exception:
            pass
    if to_date and isinstance(to_date, str):
        try:
            df = df[df["date"] <= pd.to_datetime(to_date)]
        except Exception:
            pass
    if accounts and isinstance(accounts, str):
        slugs = [s.strip() for s in accounts.split(",") if s.strip()]
        if slugs and "source" in df.columns:
            df = df[df["source"].isin(slugs)]
    return df


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# Parse endpoint
# ---------------------------------------------------------------------------

@app.post("/api/parse")
async def parse(files: list[UploadFile] = File(...)) -> JSONResponse:
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for f in files:
        filename = f.filename or "statement.pdf"
        lower_name = filename.lower()
        is_pdf = lower_name.endswith(".pdf")
        is_csv = lower_name.endswith(".csv")

        if not is_pdf and not is_csv:
            errors.append({"file": filename, "error": "Only PDF and CSV files are supported."})
            continue

        token = secrets.token_urlsafe(10)
        safe_base = _safe_stem(filename)
        out_id = token
        out_name = f"{safe_base}.csv"
        out_path = OUTPUT_DIR / f"{out_id}__{out_name}"

        try:
            content = await f.read()

            if is_pdf:
                upload_path = UPLOADS_DIR / f"{safe_base}_{token}.pdf"
                upload_path.write_bytes(content)
                df = parse_file(upload_path)
            else:
                upload_path = UPLOADS_DIR / f"{safe_base}_{token}.csv"
                upload_path.write_bytes(content)
                source = detect_source(upload_path)
                df = parse_file(upload_path, source_hint=source)
                if df.empty or "date" not in df.columns:
                    csv_text = content.decode("utf-8", errors="replace")
                    df = pd.read_csv(StringIO(csv_text))

            if "date" in df.columns or "Date" in df.columns:
                if "date" not in df.columns:
                    df = migrate_legacy_df(df)
                df = apply_categorization(df)

            out_path.write_text(df.to_csv(index=False), encoding="utf-8", newline="")

            created.append({
                "id": out_id,
                "name": out_name,
                "rows": int(df.shape[0]),
                "columns": list(df.columns),
            })
        except Exception as e:
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


# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------

@app.get("/api/files")
def list_files() -> JSONResponse:
    items: list[dict[str, Any]] = []
    for p in sorted(OUTPUT_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        if "__" in p.name:
            file_id, rest = p.name.split("__", 1)
        else:
            try:
                file_id, rest = p.name.split("_", 1)
            except ValueError:
                file_id, rest = p.stem, p.name
        items.append({"id": file_id, "filename": rest, "size": p.stat().st_size})
    return JSONResponse({"files": items})


@app.delete("/api/files")
def clear_files() -> JSONResponse:
    deleted = 0
    for path in OUTPUT_DIR.glob("*.csv"):
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return JSONResponse({"deleted": deleted})


@app.get("/api/files/{file_id}/preview")
def preview(file_id: str, limit: int = 50) -> JSONResponse:
    matches = list(OUTPUT_DIR.glob(f"{file_id}__*.csv")) or list(OUTPUT_DIR.glob(f"{file_id}_*.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail="CSV not found")

    path = matches[0]
    df = _parse_csv_for_preview(path, limit=limit)
    display_name = path.name.split("__", 1)[1] if "__" in path.name else path.name.split("_", 1)[1]
    return JSONResponse({
        "filename": display_name,
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
    })


def _parse_csv_for_preview(path: Path, limit: int) -> pd.DataFrame:
    limit = max(1, min(limit, 200))
    return pd.read_csv(path).head(limit)


@app.get("/api/files/{file_id}/download")
def download(file_id: str) -> FileResponse:
    matches = list(OUTPUT_DIR.glob(f"{file_id}__*.csv")) or list(OUTPUT_DIR.glob(f"{file_id}_*.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail="CSV not found")

    path = matches[0]
    download_name = path.name.split("__", 1)[1] if "__" in path.name else path.name.split("_", 1)[1]
    return FileResponse(path, media_type="text/csv", filename=download_name)


class CombineRequest(BaseModel):
    ids: list[str]


def _resolve_file(file_id: str) -> Path:
    matches = list(OUTPUT_DIR.glob(f"{file_id}__*.csv")) or list(OUTPUT_DIR.glob(f"{file_id}_*.csv"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"CSV not found: {file_id}")
    return matches[0]


def combine_csv_files(file_paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in file_paths]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


@app.post("/api/files/combine")
def combine(body: CombineRequest) -> StreamingResponse:
    if not body.ids:
        raise HTTPException(status_code=400, detail="No file IDs provided.")
    paths = [_resolve_file(fid) for fid in body.ids]
    combined = combine_csv_files(paths)
    csv_bytes = combined.to_csv(index=False).encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="combined_statements.csv"'},
    )


# ---------------------------------------------------------------------------
# Reports page & API
# ---------------------------------------------------------------------------

@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request) -> Any:
    return templates.TemplateResponse("reports.html", {"request": request})


def _reports_df(from_: Optional[str], to: Optional[str], accounts: Optional[str]) -> pd.DataFrame:
    df = _load_all_outputs()
    return _filter_df(df, from_, to, accounts)


@app.get("/api/reports/summary")
def reports_summary(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    accounts: Optional[str] = Query(None),
) -> JSONResponse:
    df = _reports_df(from_, to, accounts)
    cashflow_df = _cashflow_df(df)
    if cashflow_df.empty:
        return JSONResponse({"total_income": 0, "total_spending": 0, "net": 0, "top_category": None, "period": None, "account_breakdown": []})

    total_income = float(cashflow_df["credits"].sum())
    total_spending = float(cashflow_df["debits"].sum())
    net = total_income - total_spending

    top_cat = None
    if "category" in cashflow_df.columns:
        expense_rows = cashflow_df[cashflow_df["debits"] > 0]
        if not expense_rows.empty:
            top_cat = expense_rows.groupby("category")["debits"].sum().idxmax()

    period = None
    valid_dates = df["date"].dropna()
    if not valid_dates.empty:
        period = {"from": str(valid_dates.min().date()), "to": str(valid_dates.max().date())}

    breakdown: list[dict] = []
    if "source" in cashflow_df.columns:
        for src, grp in cashflow_df.groupby("source"):
            breakdown.append({
                "source": src,
                "income": float(grp["credits"].sum()),
                "spending": float(grp["debits"].sum()),
            })

    return JSONResponse({
        "total_income": round(total_income, 2),
        "total_spending": round(total_spending, 2),
        "net": round(net, 2),
        "top_category": top_cat,
        "period": period,
        "account_breakdown": breakdown,
    })


@app.get("/api/reports/by-category")
def reports_by_category(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    accounts: Optional[str] = Query(None),
) -> JSONResponse:
    df = _reports_df(from_, to, accounts)
    df = _cashflow_df(df)
    if df.empty or "category" not in df.columns:
        return JSONResponse({"categories": []})

    grp = df.groupby("category").agg(
        debit_total=("debits", "sum"),
        credit_total=("credits", "sum"),
        count=("item", "count"),
    ).reset_index()

    result = [
        {
            "category": row["category"],
            "debit_total": round(float(row["debit_total"]), 2),
            "credit_total": round(float(row["credit_total"]), 2),
            "count": int(row["count"]),
        }
        for _, row in grp.iterrows()
    ]
    result.sort(key=lambda x: x["debit_total"], reverse=True)
    return JSONResponse({"categories": result})


@app.get("/api/reports/by-month")
def reports_by_month(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    accounts: Optional[str] = Query(None),
) -> JSONResponse:
    df = _reports_df(from_, to, accounts)
    df = _cashflow_df(df)
    if df.empty:
        return JSONResponse({"months": []})

    df = df.dropna(subset=["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    grp = df.groupby("month").agg(income=("credits", "sum"), spending=("debits", "sum")).reset_index()
    grp["net"] = grp["income"] - grp["spending"]
    grp = grp.sort_values("month")

    result = [
        {
            "month": row["month"],
            "income": round(float(row["income"]), 2),
            "spending": round(float(row["spending"]), 2),
            "net": round(float(row["net"]), 2),
        }
        for _, row in grp.iterrows()
    ]
    return JSONResponse({"months": result})


@app.get("/api/reports/top-items")
def reports_top_items(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    accounts: Optional[str] = Query(None),
    limit: int = Query(20),
) -> JSONResponse:
    df = _reports_df(from_, to, accounts)
    df = _cashflow_df(df)
    if df.empty or "item" not in df.columns:
        return JSONResponse({"items": []})

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except Exception:
            limit = 20

    expense_rows = df[df["debits"] > 0]
    if expense_rows.empty:
        return JSONResponse({"items": []})

    grp = expense_rows.groupby("item").agg(total=("debits", "sum"), count=("debits", "count")).reset_index()
    grp = grp.sort_values("total", ascending=False).head(limit)

    result = [
        {"item": row["item"], "total": round(float(row["total"]), 2), "count": int(row["count"])}
        for _, row in grp.iterrows()
    ]
    return JSONResponse({"items": result})
