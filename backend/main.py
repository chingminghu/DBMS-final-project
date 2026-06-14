from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .graph_builder import (
    build_focus_graph,
    build_focus_summary_graph,
    build_schema_graph,
    build_initial_clusters,
    build_prequery_processing_summary,
    build_query_summary_graph,
    expand_cluster,
    get_cluster_metadata,
    get_referenced_by_edges,
)
from .models import (
    ClusterExpandResponse,
    ClusterSummaryResponse,
    DatabaseListItem,
    DatabaseListResponse,
    DatabaseSchemaResponse,
    FocusGraphResponse,
    FocusSummaryGraphResponse,
    InitialClusteringResponse,
    PreQueryProcessingResponse,
    QuerySummaryGraphResponse,
    QuerySummaryRequest,
    SchemaGraphResponse,
    TableDetailResponse,
)
from .schema_extractor import extract_schema
from .llm_summarizer import summarize_cluster
from .storage import (
    DATABASE_FILENAMES,
    DATABASE_FILES,
    SCHEMA_CACHE,
    UPLOAD_DIR,
    get_database_path,
    list_registered_database_ids,
    load_registered_databases,
    register_database_file,
)


app = FastAPI(
    title="SchemaLens Query-aware Schema Summary API",
    description="SQLite schema extraction, weighted schema preprocessing, query-set summary graph generation, and summary node compression.",
    version="0.6.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_load_saved_databases():
    load_registered_databases()


@app.get("/")
def health_check():
    return {"status": "ok", "message": "SchemaLens API is running."}




def _load_schema_or_404(database_id: str):
    tables = SCHEMA_CACHE.get(database_id)
    if tables is not None:
        return tables

    db_path = get_database_path(database_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail="Database ID not found. Upload or select a database first.")

    try:
        tables = extract_schema(db_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load database: {exc}")

    SCHEMA_CACHE[database_id] = tables
    return tables


def _schema_response(database_id: str, tables):
    foreign_key_count = sum(len(table.foreign_keys) for table in tables)
    return DatabaseSchemaResponse(
        database_id=database_id,
        filename=DATABASE_FILENAMES.get(database_id, database_id),
        table_count=len(tables),
        foreign_key_count=foreign_key_count,
        tables=tables,
    )


@app.get("/api/databases", response_model=DatabaseListResponse)
def list_databases():
    items = []

    for database_id in list_registered_database_ids():
        tables = _load_schema_or_404(database_id)
        foreign_key_count = sum(len(table.foreign_keys) for table in tables)
        items.append(
            DatabaseListItem(
                database_id=database_id,
                filename=DATABASE_FILENAMES.get(database_id, database_id),
                table_count=len(tables),
                foreign_key_count=foreign_key_count,
            )
        )

    return DatabaseListResponse(databases=items)


@app.get("/api/databases/{database_id}", response_model=DatabaseSchemaResponse)
def get_database_schema(database_id: str):
    tables = _load_schema_or_404(database_id)
    return _schema_response(database_id, tables)


@app.post("/api/databases/upload", response_model=DatabaseSchemaResponse)
async def upload_database(file: UploadFile = File(...)):
    allowed_suffixes = {".db", ".sqlite", ".sqlite3"}
    original_filename = file.filename or "uploaded.db"
    suffix = Path(original_filename).suffix.lower()

    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Only .db, .sqlite, or .sqlite3 files are allowed.")

    database_id = f"db_{uuid4().hex[:12]}"
    saved_path = UPLOAD_DIR / f"{database_id}{suffix}"

    try:
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        tables = extract_schema(saved_path)
        foreign_key_count = sum(len(table.foreign_keys) for table in tables)

        SCHEMA_CACHE[database_id] = tables
        register_database_file(database_id, saved_path, original_filename)

        return DatabaseSchemaResponse(
            database_id=database_id,
            filename=original_filename,
            table_count=len(tables),
            foreign_key_count=foreign_key_count,
            tables=tables,
        )

    except ValueError as exc:
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        if saved_path.exists():
            saved_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process database: {exc}")

    finally:
        await file.close()


@app.get("/api/databases/{database_id}/graph", response_model=SchemaGraphResponse)
def get_schema_graph(database_id: str):
    tables = _load_schema_or_404(database_id)
    return build_schema_graph(database_id, tables, db_path=get_database_path(database_id))


@app.get("/api/databases/{database_id}/clusters/initial", response_model=InitialClusteringResponse)
def get_initial_clusters(
    database_id: str,
    max_query_tables: int = Query(5, ge=1, le=10, description="Maximum representative tables recommended as initial query set"),
    target_clusters: int | None = Query(None, ge=1, le=20, description="Optional target number of initial clusters"),
):
    tables = _load_schema_or_404(database_id)
    return build_initial_clusters(
        database_id,
        tables,
        max_query_tables=max_query_tables,
        target_cluster_count=target_clusters,
        db_path=get_database_path(database_id),
    )


@app.get("/api/databases/{database_id}/prequery", response_model=PreQueryProcessingResponse)
def get_prequery_processing_summary(
    database_id: str,
    max_query_tables: int = Query(5, ge=1, le=10, description="Maximum representative tables recommended as initial query set"),
    target_clusters: int | None = Query(None, ge=1, le=20, description="Optional target number of initial clusters"),
    top_n_tables: int = Query(8, ge=1, le=20, description="Number of top importance tables to return"),
):
    tables = _load_schema_or_404(database_id)
    return build_prequery_processing_summary(
        database_id,
        tables,
        max_query_tables=max_query_tables,
        target_cluster_count=target_clusters,
        top_n_tables=top_n_tables,
        db_path=get_database_path(database_id),
    )


@app.post("/api/databases/{database_id}/query-summary", response_model=QuerySummaryGraphResponse)
def get_query_summary_graph(database_id: str, request: QuerySummaryRequest):
    tables = _load_schema_or_404(database_id)

    try:
        return build_query_summary_graph(
            database_id,
            tables,
            query_tables=request.query_tables,
            node_budget=request.node_budget,
            include_neighbors=request.include_neighbors,
            max_query_tables=request.max_query_tables,
            db_path=get_database_path(database_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.get("/api/databases/{database_id}/focus", response_model=FocusGraphResponse)
def get_focus_graph(
    database_id: str,
    table: str = Query(..., description="Focus table name"),
    depth: int = Query(1, ge=0, le=3, description="Neighbor depth"),
):
    tables = _load_schema_or_404(database_id)

    try:
        return build_focus_graph(database_id, tables, table, depth, db_path=get_database_path(database_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/focus-summary", response_model=FocusSummaryGraphResponse)
def get_focus_summary_graph(
    database_id: str,
    table: str = Query(..., description="Focus table name"),
    depth: int = Query(1, ge=0, le=3, description="Neighbor depth"),
):
    tables = _load_schema_or_404(database_id)

    try:
        return build_focus_summary_graph(database_id, tables, table, depth, db_path=get_database_path(database_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/clusters/{cluster_id}/expand", response_model=ClusterExpandResponse)
def get_cluster_expansion(
    database_id: str,
    cluster_id: str,
    table: str = Query(..., description="Focus table name used to create the summary node"),
    depth: int = Query(1, ge=0, le=3, description="Focus depth used to create the summary node"),
):
    tables = _load_schema_or_404(database_id)

    try:
        return expand_cluster(database_id, tables, table, cluster_id, depth, db_path=get_database_path(database_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.get("/api/databases/{database_id}/clusters/{cluster_id}/summary", response_model=ClusterSummaryResponse)
def get_cluster_summary(
    database_id: str,
    cluster_id: str,
    table: str = Query(..., description="Focus table name used to create the summary node"),
    depth: int = Query(1, ge=0, le=3, description="Focus depth used to create the summary node"),
):
    tables = _load_schema_or_404(database_id)

    try:
        cluster_tables, relevant_edges = get_cluster_metadata(database_id, tables, table, cluster_id, depth, db_path=get_database_path(database_id))
        return summarize_cluster(database_id, cluster_id, cluster_tables, relevant_edges)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/databases/{database_id}/tables/{table_name}", response_model=TableDetailResponse)
def get_table_detail(database_id: str, table_name: str):
    tables = _load_schema_or_404(database_id)

    table = next((item for item in tables if item.name == table_name), None)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    graph = build_schema_graph(database_id, tables, db_path=get_database_path(database_id))
    node = next((item for item in graph.nodes if item.id == table_name), None)
    outgoing_edges = [edge for edge in graph.edges if edge.source == table_name]

    return TableDetailResponse(
        database_id=database_id,
        table=table,
        node=node,
        outgoing_edges=outgoing_edges,
        referenced_by=get_referenced_by_edges(database_id, table_name, tables, db_path=get_database_path(database_id)),
    )
