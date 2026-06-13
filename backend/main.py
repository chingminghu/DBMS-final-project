from pathlib import Path
from datetime import datetime
from uuid import uuid4
import shutil

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .graph_builder import (
    build_focus_graph,
    build_focus_summary_graph,
    build_schema_graph,
    expand_cluster,
    get_cluster_metadata,
    get_referenced_by_edges,
)
from .models import (
    ClusterExpandResponse,
    ClusterSummaryResponse,
    DatabaseSchemaResponse,
    FocusGraphResponse,
    FocusSummaryGraphResponse,
    SchemaGraphResponse,
    TableDetailResponse,
)
from .schema_extractor import extract_schema
from .llm_summarizer import summarize_cluster
from .storage import DATABASE_FILENAMES, DATABASE_FILES, SCHEMA_CACHE, UPLOAD_DIR


class DebugLogRequest(BaseModel):
    event_type: str
    message: str
    payload: dict | None = None


def print_debug_log(source: str, event_type: str, message: str, payload: dict | None = None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[SchemaLens Debug][{timestamp}][{source}][{event_type}] {message}")
    if payload:
        print(f"[SchemaLens Debug][payload] {payload}")


app = FastAPI(
    title="SchemaLens Step 5 API",
    description="SQLite schema extraction, focus view, and summary node compression.",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "SchemaLens Step 5 API is running."}


@app.post("/api/debug/log")
def debug_log(log: DebugLogRequest):
    """Receive frontend debug logs and print them to the backend terminal."""
    print_debug_log(
        source="frontend",
        event_type=log.event_type,
        message=log.message,
        payload=log.payload,
    )
    return {"status": "ok"}


@app.post("/api/databases/upload", response_model=DatabaseSchemaResponse)
async def upload_database(file: UploadFile = File(...)):
    allowed_suffixes = {".db", ".sqlite", ".sqlite3"}
    original_filename = file.filename or "uploaded.db"
    suffix = Path(original_filename).suffix.lower()

    print_debug_log("backend", "upload_start", f"Uploading database file: {original_filename}")

    if suffix not in allowed_suffixes:
        print_debug_log("backend", "upload_error", "Invalid database file extension", {"filename": original_filename})
        raise HTTPException(status_code=400, detail="Only .db, .sqlite, or .sqlite3 files are allowed.")

    database_id = f"db_{uuid4().hex[:12]}"
    saved_path = UPLOAD_DIR / f"{database_id}{suffix}"

    try:
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        tables = extract_schema(saved_path)
        foreign_key_count = sum(len(table.foreign_keys) for table in tables)

        SCHEMA_CACHE[database_id] = tables
        DATABASE_FILES[database_id] = saved_path
        DATABASE_FILENAMES[database_id] = original_filename

        print_debug_log(
            "backend",
            "upload_success",
            f"Database parsed successfully: {original_filename}",
            {
                "database_id": database_id,
                "table_count": len(tables),
                "foreign_key_count": foreign_key_count,
            },
        )

        return DatabaseSchemaResponse(
            database_id=database_id,
            filename=original_filename,
            table_count=len(tables),
            foreign_key_count=foreign_key_count,
            tables=tables,
        )

    except ValueError as exc:
        print_debug_log("backend", "upload_error", str(exc), {"filename": original_filename})
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        print_debug_log("backend", "upload_error", str(exc), {"filename": original_filename})
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process database: {exc}")

    finally:
        await file.close()


@app.get("/api/databases/{database_id}/graph", response_model=SchemaGraphResponse)
def get_schema_graph(database_id: str):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")
    return build_schema_graph(database_id, tables)


@app.get("/api/databases/{database_id}/focus", response_model=FocusGraphResponse)
def get_focus_graph(
    database_id: str,
    table: str = Query(..., description="Focus table name"),
    depth: int = Query(1, ge=0, le=3, description="Neighbor depth"),
):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")

    try:
        return build_focus_graph(database_id, tables, table, depth)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/focus-summary", response_model=FocusSummaryGraphResponse)
def get_focus_summary_graph(
    database_id: str,
    table: str = Query(..., description="Focus table name"),
    depth: int = Query(1, ge=0, le=3, description="Neighbor depth"),
):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")

    try:
        print_debug_log(
            "backend",
            "focus_summary_request",
            f"Build focus-summary graph for table={table}, depth={depth}",
            {"database_id": database_id},
        )
        return build_focus_summary_graph(database_id, tables, table, depth)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/clusters/{cluster_id}/expand", response_model=ClusterExpandResponse)
def get_cluster_expansion(
    database_id: str,
    cluster_id: str,
    table: str = Query(..., description="Focus table name used to create the summary node"),
    depth: int = Query(1, ge=0, le=3, description="Focus depth used to create the summary node"),
):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")

    try:
        return expand_cluster(database_id, tables, table, cluster_id, depth)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.get("/api/databases/{database_id}/clusters/{cluster_id}/summary", response_model=ClusterSummaryResponse)
def get_cluster_summary(
    database_id: str,
    cluster_id: str,
    table: str = Query(..., description="Focus table name used to create the summary node"),
    depth: int = Query(1, ge=0, le=3, description="Focus depth used to create the summary node"),
):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")

    try:
        print_debug_log(
            "backend",
            "cluster_summary_request",
            f"Summarize cluster={cluster_id}, focus_table={table}, depth={depth}",
            {"database_id": database_id},
        )
        cluster_tables, relevant_edges = get_cluster_metadata(database_id, tables, table, cluster_id, depth)
        return summarize_cluster(database_id, cluster_id, cluster_tables, relevant_edges)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/tables/{table_name}", response_model=TableDetailResponse)
def get_table_detail(database_id: str, table_name: str):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload a database first.")

    table = next((item for item in tables if item.name == table_name), None)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    return TableDetailResponse(
        database_id=database_id,
        table=table,
        referenced_by=get_referenced_by_edges(database_id, table_name, tables),
    )
