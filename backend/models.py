from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Literal


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


class DatabaseListItem(BaseModel):
    database_id: str
    filename: str
    table_count: int
    foreign_key_count: int


class DatabaseListResponse(BaseModel):
    databases: List[DatabaseListItem]


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: Literal["table", "focus", "summary", "query", "bridge"] = "table"
    column_count: int = 0
    primary_keys: List[str] = []
    foreign_key_count: int = 0
    referenced_by_count: int = 0
    row_count: Optional[int] = None
    table_count: Optional[int] = None
    tables: Optional[List[str]] = None
    description: Optional[str] = None
    importance_score: float = 0.0
    score_breakdown: Dict[str, float] = {}
    representative_table: Optional[str] = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    edge_type: Literal["foreign_key", "summary_edge", "metaedge"] = "foreign_key"
    from_column: Optional[str] = None
    to_column: Optional[str] = None
    label: str
    hidden_edge_count: Optional[int] = None
    hidden_edges: Optional[List[str]] = None
    score: float = 0.0
    weight: float = 1.0
    score_breakdown: Dict[str, Any] = {}


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




class QuerySummaryRequest(BaseModel):
    query_tables: List[str]
    node_budget: int = 12
    include_neighbors: bool = True
    max_query_tables: int = 8


class SummaryNodeExpandRequest(BaseModel):
    cluster_id: str
    tables: List[str]
    visible_table_ids: List[str] = []
    direct_expand_threshold: int = 4


class QueryPathEdgeItem(BaseModel):
    source: str
    target: str
    edge_id: str
    label: str
    score: float = 0.0
    weight: float = 1.0


class QueryPathItem(BaseModel):
    source: str
    target: str
    path: List[str]
    path_edges: List[QueryPathEdgeItem] = []
    total_weight: float = 0.0
    average_edge_score: float = 0.0
    edge_count: int = 0


class QuerySummaryStats(BaseModel):
    original_node_count: int
    original_edge_count: int
    query_node_count: int
    bridge_node_count: int
    context_node_count: int
    visible_table_count: int
    summary_node_count: int
    hidden_table_count: int
    compressed_edge_count: int = 0
    budget_requested: int
    budget_respected: bool = True
    node_reduction_ratio: float = 0.0
    edge_reduction_ratio: float = 0.0


class QuerySummaryMethodSpec(BaseModel):
    graph_level: Literal["schema"] = "schema"
    edge_weighting: str = "paper-exact MI column-level path distance: wt(R,S)=min sum D(Ci,Cj), D=1-I/H"
    visible_graph_selection: str = "paper original IP-style summary graph: select query nodes, budget nodes, and order-preserving metaedges over query shortest-path union"
    hidden_compression: str = "project extension: non-selected tables are assigned to nearest visible anchors and collapsed into expandable summary nodes"
    prompt_stage_ready: bool = True


class QuerySummaryGraphResponse(BaseModel):
    database_id: str
    query_tables: List[str]
    node_budget: int
    actual_visible_table_count: int
    query_node_count: int
    bridge_node_count: int
    context_node_count: int
    summary_node_count: int
    hidden_node_count: int
    visible_table_ids: List[str]
    bridge_table_ids: List[str]
    context_table_ids: List[str]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    paths: List[QueryPathItem]
    stats: QuerySummaryStats
    method_spec: QuerySummaryMethodSpec = QuerySummaryMethodSpec()
    method_notes: List[str] = []

class ClusterExpandResponse(BaseModel):
    database_id: str
    cluster_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class SchemaCluster(BaseModel):
    cluster_id: str
    label: str
    table_count: int
    tables: List[str]
    representative_table: str
    representative_score: float = 0.0
    average_importance_score: float = 0.0
    internal_edge_score: float = 0.0
    query_set_candidate: bool = False
    modularity_contribution: float = 0.0
    e_ii: float = 0.0
    a_i: float = 0.0
    internal_edge_weight: float = 0.0
    incident_edge_weight: float = 0.0


class InitialClusteringResponse(BaseModel):
    database_id: str
    table_count: int
    edge_count: int
    cluster_count: int
    target_cluster_count: int
    recommended_query_set: List[str]
    clusters: List[SchemaCluster]
    clustering_method: str = "paper_greedy_weighted_modularity"
    modularity_score: float = 0.0
    total_edge_strength: float = 0.0
    merge_count: int = 0
    merge_history: List[Dict[str, Any]] = []




class TableImportanceItem(BaseModel):
    table: str
    importance_score: float
    rank: int
    row_count: Optional[int] = None
    degree: int = 0
    referenced_by_count: int = 0
    foreign_key_count: int = 0
    reason: str = ""


class EdgeWeightSummary(BaseModel):
    edge_count: int
    min_score: float = 0.0
    max_score: float = 0.0
    average_score: float = 0.0
    min_weight: float = 0.0
    max_weight: float = 0.0
    average_weight: float = 0.0
    strongest_edges: List[GraphEdge] = []


class PreQueryProcessingResponse(BaseModel):
    database_id: str
    table_count: int
    edge_count: int
    target_cluster_count: int
    recommended_query_set: List[str]
    top_importance_tables: List[TableImportanceItem]
    edge_weight_summary: EdgeWeightSummary
    clusters: List[SchemaCluster]
    method_notes: List[str] = []

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
    node: Optional[GraphNode] = None
    outgoing_edges: List[GraphEdge] = []
    referenced_by: List[GraphEdge]
