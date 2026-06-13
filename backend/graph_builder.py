from collections import defaultdict, deque
from typing import List, Dict, Set, Tuple

from .models import (
    TableMeta,
    GraphNode,
    GraphEdge,
    SchemaGraphResponse,
    FocusGraphResponse,
    FocusSummaryGraphResponse,
    ClusterExpandResponse,
)


def build_schema_graph(database_id: str, tables: List[TableMeta]) -> SchemaGraphResponse:
    referenced_by_count: Dict[str, int] = defaultdict(int)
    edges: List[GraphEdge] = []

    for table in tables:
        for fk_index, fk in enumerate(table.foreign_keys):
            referenced_by_count[fk.table] += 1
            edge_id = (
                f"fk__{table.name}__{fk.from_column}"
                f"__to__{fk.table}__{fk.to_column}__{fk.id}_{fk.seq}_{fk_index}"
            )
            edges.append(
                GraphEdge(
                    id=edge_id,
                    source=table.name,
                    target=fk.table,
                    from_column=fk.from_column,
                    to_column=fk.to_column,
                    label=f"{table.name}.{fk.from_column} → {fk.table}.{fk.to_column}",
                )
            )

    nodes: List[GraphNode] = []
    for table in tables:
        nodes.append(
            GraphNode(
                id=table.name,
                label=table.name,
                node_type="table",
                column_count=len(table.columns),
                primary_keys=table.primary_keys,
                foreign_key_count=len(table.foreign_keys),
                referenced_by_count=referenced_by_count[table.name],
                row_count=table.row_count,
            )
        )

    return SchemaGraphResponse(
        database_id=database_id,
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=nodes,
        edges=edges,
    )


def get_referenced_by_edges(database_id: str, table_name: str, tables: List[TableMeta]) -> List[GraphEdge]:
    graph = build_schema_graph(database_id, tables)
    return [edge for edge in graph.edges if edge.target == table_name]


def _build_undirected_adjacency(edges: List[GraphEdge]) -> Dict[str, Set[str]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    for edge in edges:
        adj[edge.source].add(edge.target)
        adj[edge.target].add(edge.source)
    return adj


def _nodes_within_depth(focus_table: str, edges: List[GraphEdge], depth: int) -> Set[str]:
    if depth < 0:
        depth = 0

    adj = _build_undirected_adjacency(edges)
    visible: Set[str] = {focus_table}
    queue = deque([(focus_table, 0)])

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for neighbor in adj.get(current, set()):
            if neighbor not in visible:
                visible.add(neighbor)
                queue.append((neighbor, current_depth + 1))

    return visible


def build_focus_graph(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    depth: int = 1,
) -> FocusGraphResponse:
    graph = build_schema_graph(database_id, tables)
    node_map = {node.id: node for node in graph.nodes}

    if focus_table not in node_map:
        raise KeyError(f"Table not found: {focus_table}")

    visible_ids = _nodes_within_depth(focus_table, graph.edges, depth)
    hidden_ids = set(node_map.keys()) - visible_ids

    visible_nodes: List[GraphNode] = []
    for node_id in sorted(visible_ids):
        node = node_map[node_id]
        if node.id == focus_table:
            node = node.model_copy(update={"node_type": "focus"})
        visible_nodes.append(node)

    visible_edges = [
        edge for edge in graph.edges
        if edge.source in visible_ids and edge.target in visible_ids
    ]

    hidden_edges = [
        edge for edge in graph.edges
        if edge.source in hidden_ids or edge.target in hidden_ids
    ]

    return FocusGraphResponse(
        database_id=database_id,
        focus_table=focus_table,
        depth=depth,
        total_node_count=graph.node_count,
        total_edge_count=graph.edge_count,
        visible_node_count=len(visible_nodes),
        visible_edge_count=len(visible_edges),
        hidden_node_count=len(hidden_ids),
        hidden_edge_count=len(hidden_edges),
        visible_nodes=visible_nodes,
        visible_edges=visible_edges,
        hidden_nodes=sorted(hidden_ids),
    )


def _connected_components(nodes: Set[str], edges: List[GraphEdge]) -> List[Set[str]]:
    if not nodes:
        return []

    adj: Dict[str, Set[str]] = {node: set() for node in nodes}
    for edge in edges:
        if edge.source in nodes and edge.target in nodes:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

    seen: Set[str] = set()
    components: List[Set[str]] = []

    for node in sorted(nodes):
        if node in seen:
            continue

        comp: Set[str] = set()
        queue = deque([node])
        seen.add(node)

        while queue:
            current = queue.popleft()
            comp.add(current)
            for nb in adj.get(current, set()):
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)

        components.append(comp)

    return components


def _guess_cluster_label(cluster_tables: List[str]) -> str:
    joined = " ".join(cluster_tables).lower()

    keyword_groups = [
        (["order", "payment", "shipment", "customer"], "Order / Customer module"),
        (["product", "category", "supplier", "stock", "inventory"], "Product / Inventory module"),
        (["student", "teacher", "course", "enrollment", "attendance", "department"], "Education module"),
        (["ticket", "reply", "review", "support", "feedback"], "Support / Feedback module"),
        (["user", "profile", "login", "account", "session"], "User / Account module"),
        (["log", "audit", "event"], "Logs / Audit module"),
    ]

    for keywords, label in keyword_groups:
        if any(keyword in joined for keyword in keywords):
            return label

    return f"Schema group ({len(cluster_tables)} tables)"


def _build_summary_nodes(
    hidden_ids: Set[str],
    graph: SchemaGraphResponse,
) -> Tuple[List[GraphNode], Dict[str, Set[str]], Set[str]]:
    """Compress only hidden components with 2+ tables.

    If a component has only one table, return that table as singleton_ids.
    It will be displayed as a normal table node instead of a summary node.
    """
    components = _connected_components(hidden_ids, graph.edges)
    cluster_map: Dict[str, Set[str]] = {}
    singleton_ids: Set[str] = set()
    summary_nodes: List[GraphNode] = []
    summary_index = 1

    for comp in components:
        if len(comp) == 1:
            singleton_ids.update(comp)
            continue

        cluster_id = f"summary_{summary_index}"
        summary_index += 1
        cluster_tables = sorted(comp)
        label = _guess_cluster_label(cluster_tables)
        cluster_map[cluster_id] = set(cluster_tables)

        summary_nodes.append(
            GraphNode(
                id=cluster_id,
                label=label,
                node_type="summary",
                table_count=len(cluster_tables),
                tables=cluster_tables,
                description=f"Collapsed subgraph containing {len(cluster_tables)} table(s).",
            )
        )

    return summary_nodes, cluster_map, singleton_ids


def _build_compressed_edges(
    visible_ids: Set[str],
    cluster_map: Dict[str, Set[str]],
    visible_edges: List[GraphEdge],
    graph: SchemaGraphResponse,
) -> List[GraphEdge]:
    compressed_edges = list(visible_edges)
    existing = {edge.id for edge in compressed_edges}
    bucket: Dict[Tuple[str, str], List[GraphEdge]] = defaultdict(list)

    for edge in graph.edges:
        for cluster_id, cluster_tables in cluster_map.items():
            if edge.source in visible_ids and edge.target in cluster_tables:
                bucket[(edge.source, cluster_id)].append(edge)
            elif edge.target in visible_ids and edge.source in cluster_tables:
                bucket[(cluster_id, edge.target)].append(edge)

    for (source, target), hidden_edges in bucket.items():
        edge_id = f"summary_edge__{source}__to__{target}"
        if edge_id in existing:
            continue
        labels = [edge.label for edge in hidden_edges]
        compressed_edges.append(
            GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                edge_type="summary_edge",
                label=f"{len(hidden_edges)} hidden relationship(s)",
                hidden_edge_count=len(hidden_edges),
                hidden_edges=labels,
            )
        )
        existing.add(edge_id)

    return compressed_edges


def build_focus_summary_graph(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    depth: int = 1,
) -> FocusSummaryGraphResponse:
    graph = build_schema_graph(database_id, tables)
    node_map = {node.id: node for node in graph.nodes}

    if focus_table not in node_map:
        raise KeyError(f"Table not found: {focus_table}")

    visible_ids = _nodes_within_depth(focus_table, graph.edges, depth)
    hidden_ids = set(node_map.keys()) - visible_ids

    visible_nodes: List[GraphNode] = []
    for node_id in sorted(visible_ids):
        node = node_map[node_id]
        if node.id == focus_table:
            node = node.model_copy(update={"node_type": "focus"})
        visible_nodes.append(node)

    visible_edges = [
        edge for edge in graph.edges
        if edge.source in visible_ids and edge.target in visible_ids
    ]

    summary_nodes, cluster_map, singleton_ids = _build_summary_nodes(hidden_ids, graph)
    singleton_nodes = [node_map[node_id] for node_id in sorted(singleton_ids)]

    # Single-table hidden components are shown directly as normal table nodes.
    visible_plus_singletons = visible_ids | singleton_ids

    base_edges = [
        edge for edge in graph.edges
        if edge.source in visible_plus_singletons and edge.target in visible_plus_singletons
    ]

    compressed_edges = _build_compressed_edges(visible_plus_singletons, cluster_map, base_edges, graph)
    all_nodes = visible_nodes + singleton_nodes + summary_nodes

    return FocusSummaryGraphResponse(
        database_id=database_id,
        focus_table=focus_table,
        depth=depth,
        total_node_count=graph.node_count,
        total_edge_count=graph.edge_count,
        visible_node_count=len(visible_nodes) + len(singleton_nodes),
        summary_node_count=len(summary_nodes),
        hidden_node_count=sum(len(v) for v in cluster_map.values()),
        nodes=all_nodes,
        edges=compressed_edges,
    )


def expand_cluster(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    cluster_id: str,
    depth: int = 1,
) -> ClusterExpandResponse:
    graph = build_schema_graph(database_id, tables)
    node_map = {node.id: node for node in graph.nodes}

    visible_ids = _nodes_within_depth(focus_table, graph.edges, depth)
    hidden_ids = set(node_map.keys()) - visible_ids
    _, cluster_map, singleton_ids = _build_summary_nodes(hidden_ids, graph)

    if cluster_id not in cluster_map:
        raise KeyError(f"Cluster not found: {cluster_id}")

    cluster_tables = cluster_map[cluster_id]
    nodes = [node_map[node_id] for node_id in sorted(cluster_tables)]

    # Return internal cluster edges plus boundary edges back to the already visible graph.
    # Include singleton nodes too because they are displayed as real nodes in the compressed view.
    visible_or_passthrough = visible_ids | singleton_ids
    allowed_nodes = cluster_tables | visible_or_passthrough

    edges = [
        edge for edge in graph.edges
        if edge.source in allowed_nodes
        and edge.target in allowed_nodes
        and (edge.source in cluster_tables or edge.target in cluster_tables)
    ]

    return ClusterExpandResponse(
        database_id=database_id,
        cluster_id=cluster_id,
        nodes=nodes,
        edges=edges,
    )



def get_cluster_metadata(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    cluster_id: str,
    depth: int = 1,
) -> Tuple[List[TableMeta], List[GraphEdge]]:
    """Return the TableMeta list and relevant edges for a summary cluster.

    This is used by LLM summary generation. It intentionally shares the same
    clustering logic as focus-summary and expand_cluster, so the summary always
    describes the exact cluster represented by the clicked summary node.
    """
    graph = build_schema_graph(database_id, tables)
    table_map = {table.name: table for table in tables}
    node_map = {node.id: node for node in graph.nodes}

    if focus_table not in node_map:
        raise KeyError(f"Table not found: {focus_table}")

    visible_ids = _nodes_within_depth(focus_table, graph.edges, depth)
    hidden_ids = set(node_map.keys()) - visible_ids
    _, cluster_map, singleton_ids = _build_summary_nodes(hidden_ids, graph)

    if cluster_id not in cluster_map:
        raise KeyError(f"Cluster not found: {cluster_id}")

    cluster_tables = cluster_map[cluster_id]
    cluster_table_meta = [table_map[name] for name in sorted(cluster_tables) if name in table_map]

    visible_or_passthrough = visible_ids | singleton_ids
    allowed_nodes = cluster_tables | visible_or_passthrough

    relevant_edges = [
        edge for edge in graph.edges
        if edge.source in allowed_nodes
        and edge.target in allowed_nodes
        and (edge.source in cluster_tables or edge.target in cluster_tables)
    ]

    return cluster_table_meta, relevant_edges
