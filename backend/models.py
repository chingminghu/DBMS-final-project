from pydantic import BaseModel
from typing import List, Optional, Literal


class ColumnMeta(BaseModel):
    name: str
    type: str
    not_null: bool
    default_value: Optional[str] = None
    primary_key_position: int = 0
    is_primary_key: bool = False


class ForeignKeyMeta(BaseModel):
    id: int
    seq: int
    table: str
    from_column: str
    to_column: str
    on_update: str
    on_delete: str
    match: str


class TableMeta(BaseModel):
    name: str
    columns: List[ColumnMeta]
    primary_keys: List[str]
    foreign_keys: List[ForeignKeyMeta]
    row_count: Optional[int] = None


class DatabaseSchemaResponse(BaseModel):
    database_id: str
    filename: str
    table_count: int
    foreign_key_count: int
    tables: List[TableMeta]


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: Literal["table", "focus", "summary"] = "table"
    column_count: int = 0
    primary_keys: List[str] = []
    foreign_key_count: int = 0
    referenced_by_count: int = 0
    row_count: Optional[int] = None
    table_count: Optional[int] = None
    tables: Optional[List[str]] = None
    description: Optional[str] = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    edge_type: Literal["foreign_key", "summary_edge"] = "foreign_key"
    from_column: Optional[str] = None
    to_column: Optional[str] = None
    label: str
    hidden_edge_count: Optional[int] = None
    hidden_edges: Optional[List[str]] = None


class SchemaGraphResponse(BaseModel):
    database_id: str
    node_count: int
    edge_count: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class FocusGraphResponse(BaseModel):
    database_id: str
    focus_table: str
    depth: int
    total_node_count: int
    total_edge_count: int
    visible_node_count: int
    visible_edge_count: int
    hidden_node_count: int
    hidden_edge_count: int
    visible_nodes: List[GraphNode]
    visible_edges: List[GraphEdge]
    hidden_nodes: List[str]


class FocusSummaryGraphResponse(BaseModel):
    database_id: str
    focus_table: str
    depth: int
    total_node_count: int
    total_edge_count: int
    visible_node_count: int
    summary_node_count: int
    hidden_node_count: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class ClusterExpandResponse(BaseModel):
    database_id: str
    cluster_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]



class ClusterSummaryResponse(BaseModel):
    database_id: str
    cluster_id: str
    module_name_zh: str
    description_zh: str
    key_tables: List[str]
    reason_zh: str
    source: Literal["llm", "fallback"] = "fallback"


class TableDetailResponse(BaseModel):
    database_id: str
    table: TableMeta
    referenced_by: List[GraphEdge]
