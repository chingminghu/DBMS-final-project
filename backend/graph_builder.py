from collections import Counter, defaultdict, deque
import itertools
import math
import sqlite3
from pathlib import Path
from typing import Any, List, Dict, Optional, Set, Tuple

from .models import (
    TableMeta,
    GraphNode,
    GraphEdge,
    SchemaGraphResponse,
    FocusGraphResponse,
    FocusSummaryGraphResponse,
    ClusterExpandResponse,
    InitialClusteringResponse,
    SchemaCluster,
    TableImportanceItem,
    EdgeWeightSummary,
    PreQueryProcessingResponse,
    QuerySummaryGraphResponse,
    QueryPathItem,
    QueryPathEdgeItem,
    QuerySummaryStats,
    QuerySummaryMethodSpec,
)




EDGE_PROFILE_SAMPLE_LIMIT = 5000


def _quote_identifier(identifier: str) -> str:
    """Quote a SQLite identifier safely for generated profiling queries."""
    return '"' + identifier.replace('"', '""') + '"'


def _entropy(values: List[Any]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log(p, 2)
    return entropy


def _mutual_information(xs: List[Any], ys: List[Any]) -> Tuple[float, float, float, float]:
    """Return (MI, H(X), H(Y), H(X,Y)) for sampled paired column values."""
    if not xs or not ys or len(xs) != len(ys):
        return 0.0, 0.0, 0.0, 0.0
    h_x = _entropy(xs)
    h_y = _entropy(ys)
    h_xy = _entropy(list(zip(xs, ys)))
    mi = max(0.0, h_x + h_y - h_xy)
    return mi, h_x, h_y, h_xy


def _value_key(value: Any) -> str:
    if value is None:
        return "__NULL__"
    text = str(value)
    if len(text) > 120:
        text = text[:120]
    return text



def _pair_counts_metrics(pair_counts: Counter) -> Dict[str, float]:
    """Compute paper MI / entropy / distance from a joint distribution.

    Paper formula:
        D(X,Y) = 1 - I(X,Y) / H(X,Y)
    where I and H are computed over the supplied joint distribution.
    """
    total = float(sum(pair_counts.values()))
    if total <= 0:
        return {
            "mutual_information": 0.0,
            "joint_entropy": 0.0,
            "source_entropy": 0.0,
            "target_entropy": 0.0,
            "information_distance": 1.0,
            "information_strength": 0.0,
            "sample_size": 0.0,
        }

    x_counts: Counter = Counter()
    y_counts: Counter = Counter()
    for (x, y), count in pair_counts.items():
        x_counts[x] += count
        y_counts[y] += count

    h_x = 0.0
    h_y = 0.0
    h_xy = 0.0
    mi = 0.0
    for count in x_counts.values():
        p = count / total
        h_x -= p * math.log(p, 2)
    for count in y_counts.values():
        p = count / total
        h_y -= p * math.log(p, 2)
    for (x, y), count in pair_counts.items():
        p_xy = count / total
        h_xy -= p_xy * math.log(p_xy, 2)
        p_x = x_counts[x] / total
        p_y = y_counts[y] / total
        if p_xy > 0 and p_x > 0 and p_y > 0:
            mi += p_xy * math.log(p_xy / (p_x * p_y), 2)

    if h_xy <= 1e-12:
        distance = 1.0
    else:
        distance = 1.0 - (mi / h_xy)
    distance = max(0.0, min(1.0, distance))
    return {
        "mutual_information": round(max(0.0, mi), 6),
        "joint_entropy": round(h_xy, 6),
        "source_entropy": round(h_x, 6),
        "target_entropy": round(h_y, 6),
        "information_distance": round(distance, 6),
        "information_strength": round(1.0 - distance, 6),
        "sample_size": float(total),
    }


def _fetch_projection_pair_counts(
    conn: sqlite3.Connection,
    table_name: str,
    left_columns: List[str],
    right_columns: List[str],
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Counter:
    """Joint distribution from same-table projection, as in the paper."""
    table_q = _quote_identifier(table_name)
    select_exprs = []
    for idx, col in enumerate(left_columns):
        select_exprs.append(f"{_quote_identifier(col)} AS l{idx}")
    for idx, col in enumerate(right_columns):
        select_exprs.append(f"{_quote_identifier(col)} AS r{idx}")
    rows = conn.execute(
        f"SELECT {', '.join(select_exprs)} FROM {table_q} LIMIT ?",
        (sample_limit,),
    ).fetchall()
    counts: Counter = Counter()
    for row in rows:
        left = tuple(_value_key(row[f"l{idx}"]) for idx in range(len(left_columns)))
        right = tuple(_value_key(row[f"r{idx}"]) for idx in range(len(right_columns)))
        if len(left) == 1:
            left = left[0]
        if len(right) == 1:
            right = right[0]
        counts[(left, right)] += 1
    return counts


def _fetch_column_value_counts(
    conn: sqlite3.Connection,
    table_name: str,
    columns: List[str],
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Counter:
    table_q = _quote_identifier(table_name)
    select_exprs = [f"{_quote_identifier(col)} AS c{idx}" for idx, col in enumerate(columns)]
    rows = conn.execute(
        f"SELECT {', '.join(select_exprs)} FROM {table_q} LIMIT ?",
        (sample_limit,),
    ).fetchall()
    counts: Counter = Counter()
    for row in rows:
        value = tuple(_value_key(row[f"c{idx}"]) for idx in range(len(columns)))
        if len(value) == 1:
            value = value[0]
        counts[value] += 1
    return counts


def _paper_column_distance_same_table(
    conn: sqlite3.Connection,
    table_name: str,
    left_columns: List[str],
    right_columns: List[str],
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Dict[str, float]:
    if not left_columns or not right_columns or left_columns == right_columns:
        return {
            "mutual_information": 0.0,
            "joint_entropy": 0.0,
            "source_entropy": 0.0,
            "target_entropy": 0.0,
            "information_distance": 0.0,
            "information_strength": 1.0,
            "sample_size": 0.0,
        }
    counts = _fetch_projection_pair_counts(conn, table_name, left_columns, right_columns, sample_limit)
    return _pair_counts_metrics(counts)


def _paper_column_distance_full_outer_join(
    conn: sqlite3.Connection,
    source_table: str,
    source_columns: List[str],
    target_table: str,
    target_columns: List[str],
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Dict[str, float]:
    """Joint distribution for columns from different tables via full outer join.

    The paper proposes full outer join rather than inner join so unmatched values
    are represented as (value, NULL) or (NULL, value) and are penalized.
    """
    source_counts = _fetch_column_value_counts(conn, source_table, source_columns, sample_limit)
    target_counts = _fetch_column_value_counts(conn, target_table, target_columns, sample_limit)
    pair_counts: Counter = Counter()

    source_keys = set(source_counts.keys())
    target_keys = set(target_counts.keys())
    for value, sx in source_counts.items():
        ty = target_counts.get(value, 0)
        if ty > 0:
            pair_counts[(value, value)] += sx * ty
        else:
            pair_counts[(value, "__NULL_TARGET__")] += sx
    for value, ty in target_counts.items():
        if value not in source_keys:
            pair_counts[("__NULL_SOURCE__", value)] += ty

    metrics = _pair_counts_metrics(pair_counts)
    source_total = sum(source_counts.values()) or 1
    non_null_source = sum(count for value, count in source_counts.items() if value != "__NULL__")
    matched_source = sum(count for value, count in source_counts.items() if value in target_keys)
    metrics.update({
        "source_value_count": float(sum(source_counts.values())),
        "target_value_count": float(sum(target_counts.values())),
        "fk_coverage": round(non_null_source / source_total, 6),
        "match_ratio": round(matched_source / max(non_null_source, 1), 6),
    })
    return metrics


def _primary_key_columns(table: TableMeta) -> List[str]:
    if table.primary_keys:
        return list(table.primary_keys)
    if table.columns:
        return [table.columns[0].name]
    return []


def _profile_foreign_key_edge(
    db_path: Optional[Path],
    source_table_meta: TableMeta,
    source_column: str,
    target_table_meta: TableMeta,
    target_column: str,
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Dict[str, float]:
    """Compute the schema-edge weight exactly following the paper structure.

    Summary Graphs for Relational Database Schemas first defines the weight of
    a column-level edge as D(X,Y)=1-I(X,Y)/H(X,Y).  For a table-level edge
    (R,S), the paper uses the minimum sum of column-level weights between the
    primary keys of R and S along a path containing only columns from R and S.

    For a SQLite FK source_table.source_column -> target_table.target_column,
    we use the corresponding column-level path:
        source PK -> source FK column -> target referenced column -> target PK
    and sum the three D distances.  If the FK column or referenced column is
    already the table PK, the corresponding intra-table distance is 0.
    """
    if db_path is None:
        return {
            "profile_available": 0.0,
            "paper_schema_weight": 1.0,
            "information_distance": 1.0,
            "information_strength": 0.0,
            "mutual_information": 0.0,
            "joint_entropy": 0.0,
            "source_entropy": 0.0,
            "target_entropy": 0.0,
            "fk_coverage": 0.0,
            "match_ratio": 0.0,
            "sample_size": 0.0,
        }

    source_pk = _primary_key_columns(source_table_meta)
    target_pk = _primary_key_columns(target_table_meta)
    if not source_pk or not target_pk:
        return {
            "profile_available": 0.0,
            "paper_schema_weight": 1.0,
            "information_distance": 1.0,
            "information_strength": 0.0,
            "mutual_information": 0.0,
            "joint_entropy": 0.0,
            "source_entropy": 0.0,
            "target_entropy": 0.0,
            "fk_coverage": 0.0,
            "match_ratio": 0.0,
            "sample_size": 0.0,
        }

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        source_fk = [source_column]
        target_ref = [target_column]

        source_pk_to_fk = _paper_column_distance_same_table(
            conn, source_table_meta.name, source_pk, source_fk, sample_limit
        )
        fk_to_target = _paper_column_distance_full_outer_join(
            conn, source_table_meta.name, source_fk, target_table_meta.name, target_ref, sample_limit
        )
        target_ref_to_pk = _paper_column_distance_same_table(
            conn, target_table_meta.name, target_ref, target_pk, sample_limit
        )

        schema_weight = (
            source_pk_to_fk["information_distance"]
            + fk_to_target["information_distance"]
            + target_ref_to_pk["information_distance"]
        )
        # The paper weight is a dissimilarity: smaller means more informative.
        # score is only a UI-friendly conversion used for thickness/ranking.
        score = 1.0 / (1.0 + schema_weight)

        return {
            "profile_available": 1.0,
            "weighting_mode": "paper_exact_column_path_mi_distance",
            "paper_schema_weight": round(schema_weight, 6),
            "information_distance": round(fk_to_target["information_distance"], 6),
            "information_strength": round(fk_to_target["information_strength"], 6),
            "mutual_information": round(fk_to_target["mutual_information"], 6),
            "joint_entropy": round(fk_to_target["joint_entropy"], 6),
            "source_entropy": round(fk_to_target["source_entropy"], 6),
            "target_entropy": round(fk_to_target["target_entropy"], 6),
            "source_pk_to_fk_distance": round(source_pk_to_fk["information_distance"], 6),
            "fk_to_target_distance": round(fk_to_target["information_distance"], 6),
            "target_ref_to_pk_distance": round(target_ref_to_pk["information_distance"], 6),
            "fk_coverage": round(fk_to_target.get("fk_coverage", 0.0), 6),
            "match_ratio": round(fk_to_target.get("match_ratio", 0.0), 6),
            "sample_size": float(fk_to_target.get("sample_size", 0.0)),
            "paper_score_from_weight": round(score, 6),
            "source_pk_columns_count": float(len(source_pk)),
            "target_pk_columns_count": float(len(target_pk)),
        }
    except Exception:
        return {
            "profile_available": 0.0,
            "paper_schema_weight": 1.0,
            "information_distance": 1.0,
            "information_strength": 0.0,
            "mutual_information": 0.0,
            "joint_entropy": 0.0,
            "source_entropy": 0.0,
            "target_entropy": 0.0,
            "fk_coverage": 0.0,
            "match_ratio": 0.0,
            "sample_size": 0.0,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _normalize_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
    if not raw_scores:
        return {}

    values = list(raw_scores.values())
    min_value = min(values)
    max_value = max(values)

    if math.isclose(max_value, min_value):
        return {key: 1.0 for key in raw_scores}

    return {
        key: (value - min_value) / (max_value - min_value)
        for key, value in raw_scores.items()
    }


def _safe_log_row_count(row_count: int | None) -> float:
    return math.log((row_count or 0) + 1)


def _semantic_fk_score(from_column: str, target_table: str) -> float:
    """Lightweight approximation of semantic relationship strength.

    The full paper-inspired version can use column-value distributions and
    mutual information. For the prototype we use a deterministic name-based
    prior so every uploaded database can be scored without expensive profiling.
    """
    text = f"{from_column} {target_table}".lower()

    weak_lookup_terms = ["status", "type", "category", "role", "kind", "code"]
    strong_entity_terms = ["user", "customer", "order", "product", "student", "teacher", "course", "department"]
    log_terms = ["log", "audit", "history", "event"]

    if any(term in text for term in log_terms):
        return 0.55
    if any(term in text for term in weak_lookup_terms):
        return 0.65
    if any(term in text for term in strong_entity_terms):
        return 1.0
    return 0.85





def _column_entropy_from_sample(
    db_path: Optional[Path],
    table_name: str,
    column_name: str,
    sample_limit: int = EDGE_PROFILE_SAMPLE_LIMIT,
) -> Dict[str, float]:
    if db_path is None:
        return {"entropy": 0.0, "sample_size": 0.0}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        table_q = _quote_identifier(table_name)
        col_q = _quote_identifier(column_name)
        rows = conn.execute(
            f"SELECT {col_q} AS value FROM {table_q} LIMIT ?",
            (sample_limit,),
        ).fetchall()
        values = [_value_key(row["value"]) for row in rows]
        return {"entropy": round(_entropy(values), 6), "sample_size": float(len(values))}
    except Exception:
        return {"entropy": 0.0, "sample_size": 0.0}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _compute_paper_table_importance(
    tables: List[TableMeta],
    edges: List[GraphEdge],
    db_path: Optional[Path] = None,
    epsilon: float = 1e-10,
    max_iterations: int = 500,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """Compute table importance using the formula from the schema-summary paper.

    For each table R:
        IC(R) = log |R| + sum_{R.A in R} H(R.A)

    Then construct the transfer-information probability matrix Π:
        Π[R,S] = sum_{R.A-S.B} H(R.A) /
                 (log |R| + sum_{R.A'} q_A' H(R.A'))
        Π[R,R] = 1 - sum_{R != S} Π[R,S]

    Finally iterate V_{i+1} = V_i Π until convergence.  The returned
    importance_score is only min-max normalized for visualization; the raw
    stationary value is exposed in score_breakdown.
    """
    table_map = {table.name: table for table in tables}
    table_names = [table.name for table in tables]
    if not table_names:
        return {}, {}

    # Raw attribute entropy H(R.A), not normalized.  This follows the paper;
    # no degree/row-count heuristic is mixed into the score.
    column_entropy: Dict[str, Dict[str, float]] = defaultdict(dict)
    column_sample_size: Dict[str, Dict[str, float]] = defaultdict(dict)
    for table in tables:
        for col in table.columns:
            prof = _column_entropy_from_sample(db_path, table.name, col.name)
            column_entropy[table.name][col.name] = prof["entropy"]
            column_sample_size[table.name][col.name] = prof["sample_size"]

    row_log: Dict[str, float] = {
        table.name: math.log(max(float(table.row_count or 0), 1.0), 2)
        for table in tables
    }
    ic_raw: Dict[str, float] = {
        table.name: row_log[table.name] + sum(column_entropy[table.name].values())
        for table in tables
    }

    # q_A: total number of join edges involving attribute R.A.
    q_attr: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    edge_pairs_by_table_pair: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
    for edge in edges:
        if edge.from_column and edge.to_column:
            q_attr[edge.source][edge.from_column] += 1
            q_attr[edge.target][edge.to_column] += 1
            edge_pairs_by_table_pair[(edge.source, edge.target)].append((edge.from_column, edge.to_column))
            edge_pairs_by_table_pair[(edge.target, edge.source)].append((edge.to_column, edge.from_column))

    denominators: Dict[str, float] = {}
    for table in tables:
        join_entropy_mass = 0.0
        for col in table.columns:
            h = column_entropy[table.name].get(col.name, 0.0)
            q = q_attr[table.name].get(col.name, 0)
            join_entropy_mass += q * h
        denominators[table.name] = row_log[table.name] + join_entropy_mass

    # Π as row-stochastic transfer matrix.
    pi: Dict[str, Dict[str, float]] = {name: {other: 0.0 for other in table_names} for name in table_names}
    for source in table_names:
        denom = denominators.get(source, 0.0)
        offdiag_sum = 0.0
        if denom > 1e-12:
            neighbors = sorted({target for (src, target) in edge_pairs_by_table_pair if src == source and target != source})
            for target in neighbors:
                numerator = 0.0
                for source_col, _target_col in edge_pairs_by_table_pair.get((source, target), []):
                    numerator += column_entropy[source].get(source_col, 0.0)
                value = numerator / denom if numerator > 0 else 0.0
                pi[source][target] = value
                offdiag_sum += value
        pi[source][source] = max(0.0, 1.0 - offdiag_sum)
        # Numerical guard: normalize if rounding/data oddities make row sum > 1.
        row_sum = sum(pi[source].values())
        if row_sum <= 1e-12:
            pi[source][source] = 1.0
        elif not math.isclose(row_sum, 1.0):
            for target in table_names:
                pi[source][target] /= row_sum

    vector = {name: ic_raw.get(name, 0.0) for name in table_names}
    if sum(vector.values()) <= 1e-12:
        vector = {name: 1.0 for name in table_names}

    iterations_used = 0
    l_inf_distance = float("inf")
    for iteration in range(max_iterations):
        next_vector = {name: 0.0 for name in table_names}
        for source in table_names:
            for target in table_names:
                next_vector[target] += vector[source] * pi[source][target]
        l_inf_distance = max(abs(next_vector[name] - vector[name]) for name in table_names)
        vector = next_vector
        iterations_used = iteration + 1
        if l_inf_distance <= epsilon:
            break

    normalized = _normalize_scores(vector)
    breakdowns: Dict[str, Dict[str, float]] = {}
    for table in tables:
        entropy_sum = sum(column_entropy[table.name].values())
        avg_entropy = entropy_sum / max(len(table.columns), 1)
        outgoing_transfer = sum(pi[table.name][target] for target in table_names if target != table.name)
        breakdowns[table.name] = {
            "paper_initial_importance_ic": round(ic_raw.get(table.name, 0.0), 6),
            "paper_log_tuple_count": round(row_log.get(table.name, 0.0), 6),
            "paper_attribute_entropy_sum": round(entropy_sum, 6),
            "paper_average_attribute_entropy": round(avg_entropy, 6),
            "paper_transfer_denominator": round(denominators.get(table.name, 0.0), 6),
            "paper_self_transfer_probability": round(pi[table.name].get(table.name, 0.0), 6),
            "paper_outgoing_transfer_probability": round(outgoing_transfer, 6),
            "paper_stationary_importance_raw": round(vector.get(table.name, 0.0), 6),
            "paper_stationary_importance_normalized": round(normalized.get(table.name, 0.0), 6),
            "paper_random_walk_iterations": float(iterations_used),
            "paper_random_walk_linf_distance": round(l_inf_distance, 12),
            "profiled_column_count": float(len(table.columns)),
            "sampled_row_count": max(column_sample_size[table.name].values(), default=0.0),
        }

    return normalized, breakdowns


def build_schema_graph(database_id: str, tables: List[TableMeta], db_path: Optional[Path] = None) -> SchemaGraphResponse:
    referenced_by_count: Dict[str, int] = defaultdict(int)
    table_map = {table.name: table for table in tables}

    for table in tables:
        for fk in table.foreign_keys:
            referenced_by_count[fk.table] += 1

    # First, compute paper-exact schema edge weights.  These weights are true
    # dissimilarities: smaller values mean more informative join connections.
    edges: List[GraphEdge] = []
    for table in tables:
        for fk_index, fk in enumerate(table.foreign_keys):
            target_meta = table_map.get(fk.table)
            if target_meta is None:
                continue
            edge_id = (
                f"fk__{table.name}__{fk.from_column}"
                f"__to__{fk.table}__{fk.to_column}__{fk.id}_{fk.seq}_{fk_index}"
            )
            profile = _profile_foreign_key_edge(
                db_path=db_path,
                source_table_meta=table,
                source_column=fk.from_column,
                target_table_meta=target_meta,
                target_column=fk.to_column,
            )
            if profile.get("profile_available", 0.0) >= 1.0:
                edge_weight = max(0.0, float(profile.get("paper_schema_weight", 1.0)))
                weighting_mode = "paper_exact_column_path_mi_distance"
            else:
                # Last-resort fallback when data profiling is impossible.  The
                # model remains usable but marks the edge as non-paper fallback.
                edge_weight = 1.0
                weighting_mode = "paper_unavailable_fallback_weight_1"
            edge_score = 1.0 / (1.0 + edge_weight)
            edges.append(
                GraphEdge(
                    id=edge_id,
                    source=table.name,
                    target=fk.table,
                    from_column=fk.from_column,
                    to_column=fk.to_column,
                    label=f"{table.name}.{fk.from_column} → {fk.table}.{fk.to_column}",
                    score=round(edge_score, 4),
                    weight=round(edge_weight, 6),
                    score_breakdown={
                        **profile,
                        "weighting_mode": weighting_mode,
                        "paper_formula": "wt(R,S)=min sum D(Ci,Cj), D=1-I(X,Y)/H(X,Y)",
                    },
                )
            )

    # Then compute table importance using the paper's IC + transfer-matrix
    # random walk.  No degree/row-count/bridge heuristic is mixed in here.
    importance_scores, node_breakdowns = _compute_paper_table_importance(
        tables=tables,
        edges=edges,
        db_path=db_path,
    )

    nodes: List[GraphNode] = []
    for table in tables:
        importance = importance_scores.get(table.name, 0.0)
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
                importance_score=round(importance, 4),
                score_breakdown=node_breakdowns.get(table.name, {}),
            )
        )

    return SchemaGraphResponse(
        database_id=database_id,
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=nodes,
        edges=edges,
    )


class _DisjointSet:
    def __init__(self, items: List[str]):
        self.parent = {item: item for item in items}
        self.size = {item: 1 for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, a: str, b: str) -> bool:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return False
        if self.size[root_a] < self.size[root_b]:
            root_a, root_b = root_b, root_a
        self.parent[root_b] = root_a
        self.size[root_a] += self.size[root_b]
        return True

    def groups(self) -> List[Set[str]]:
        buckets: Dict[str, Set[str]] = defaultdict(set)
        for item in self.parent:
            buckets[self.find(item)].add(item)
        return list(buckets.values())


def _build_paper_community_graph(edges: List[GraphEdge]) -> Tuple[Dict[Tuple[str, str], float], Dict[str, float], float]:
    """Build the weighted undirected graph used by the community-detection paper.

    The Summary Graphs paper uses edge weight as an information distance where
    smaller is stronger.  The community-detection objective requires an edge
    strength, so we use the monotone conversion already exposed in the UI:
        s(u,v) = 1 / (1 + wt(u,v)).
    Multiple FK edges between the same pair of tables are summed.
    """
    adjacency_weight: Dict[Tuple[str, str], float] = defaultdict(float)
    degree: Dict[str, float] = defaultdict(float)
    for edge in edges:
        if edge.source == edge.target:
            continue
        u, v = sorted([edge.source, edge.target])
        strength = float(edge.score if edge.score is not None else 0.0)
        if strength <= 0:
            strength = 1.0 / (1.0 + max(float(edge.weight or 1.0), 0.0))
        adjacency_weight[(u, v)] += strength
        degree[u] += strength
        degree[v] += strength
    total_edge_strength = sum(adjacency_weight.values())
    return dict(adjacency_weight), dict(degree), float(total_edge_strength)


def _cluster_internal_weight(cluster: Set[str], adjacency_weight: Dict[Tuple[str, str], float]) -> float:
    total = 0.0
    cluster_set = set(cluster)
    for (u, v), weight in adjacency_weight.items():
        if u in cluster_set and v in cluster_set:
            total += weight
    return total


def _cluster_incident_weight(cluster: Set[str], degree: Dict[str, float]) -> float:
    return sum(degree.get(node, 0.0) for node in cluster)


def _cluster_between_weight(
    left: Set[str],
    right: Set[str],
    adjacency_weight: Dict[Tuple[str, str], float],
) -> float:
    left_set = set(left)
    right_set = set(right)
    total = 0.0
    for (u, v), weight in adjacency_weight.items():
        if (u in left_set and v in right_set) or (u in right_set and v in left_set):
            total += weight
    return total


def _modularity_contribution(
    cluster: Set[str],
    adjacency_weight: Dict[Tuple[str, str], float],
    degree: Dict[str, float],
    total_edge_strength: float,
) -> Tuple[float, float, float, float, float]:
    """Return (Q_i, e_ii, a_i, internal_weight, incident_weight).

    This follows the weighted modularity definition used by community detection:
        Q = sum_i (e_ii - a_i^2)
    where e_ii is the fraction of total edge weight inside cluster i, and a_i
    is the fraction of incident edge weight attached to cluster i.
    """
    if total_edge_strength <= 1e-12:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    internal = _cluster_internal_weight(cluster, adjacency_weight)
    incident = _cluster_incident_weight(cluster, degree)
    e_ii = internal / total_edge_strength
    a_i = incident / (2.0 * total_edge_strength)
    return e_ii - (a_i ** 2), e_ii, a_i, internal, incident


def _weighted_modularity(
    clusters: List[Set[str]],
    adjacency_weight: Dict[Tuple[str, str], float],
    degree: Dict[str, float],
    total_edge_strength: float,
) -> float:
    return sum(
        _modularity_contribution(cluster, adjacency_weight, degree, total_edge_strength)[0]
        for cluster in clusters
    )


def _paper_greedy_modularity_clustering(
    table_names: List[str],
    edges: List[GraphEdge],
    tolerance: float = 1e-12,
) -> Tuple[List[Set[str]], float, float, List[Dict[str, Any]], Dict[Tuple[str, str], float], Dict[str, float]]:
    """Complete greedy clustering from the community-detection formulation.

    Start with every table as its own cluster.  At each iteration, evaluate all
    cluster pairs connected by at least one weighted edge and merge the pair
    that maximizes the modularity gain ΔQ.  Stop when no merge can improve Q.
    """
    adjacency_weight, degree, total_edge_strength = _build_paper_community_graph(edges)
    clusters: List[Set[str]] = [{name} for name in sorted(table_names)]
    merge_history: List[Dict[str, Any]] = []

    if len(clusters) <= 1 or total_edge_strength <= 1e-12:
        return clusters, 0.0, total_edge_strength, merge_history, adjacency_weight, degree

    current_q = _weighted_modularity(clusters, adjacency_weight, degree, total_edge_strength)
    step = 0

    while len(clusters) > 1:
        best_pair: Optional[Tuple[int, int]] = None
        best_delta = 0.0
        best_q_after = current_q
        best_between_weight = 0.0

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                between = _cluster_between_weight(clusters[i], clusters[j], adjacency_weight)
                if between <= 0:
                    continue
                before_i = _modularity_contribution(clusters[i], adjacency_weight, degree, total_edge_strength)[0]
                before_j = _modularity_contribution(clusters[j], adjacency_weight, degree, total_edge_strength)[0]
                merged = clusters[i] | clusters[j]
                after = _modularity_contribution(merged, adjacency_weight, degree, total_edge_strength)[0]
                delta = after - before_i - before_j
                q_after = current_q + delta
                tie_breaker = (
                    delta,
                    between,
                    len(merged),
                    sorted(merged)[0],
                )
                current_best_tie = (
                    best_delta,
                    best_between_weight,
                    len(clusters[best_pair[0]] | clusters[best_pair[1]]) if best_pair else -1,
                    sorted(clusters[best_pair[0]] | clusters[best_pair[1]])[0] if best_pair else "",
                )
                if best_pair is None or tie_breaker > current_best_tie:
                    best_pair = (i, j)
                    best_delta = delta
                    best_q_after = q_after
                    best_between_weight = between

        if best_pair is None or best_delta <= tolerance:
            break

        i, j = best_pair
        left = clusters[i]
        right = clusters[j]
        merged = left | right
        step += 1
        merge_history.append({
            "step": step,
            "merged_clusters": [sorted(left), sorted(right)],
            "new_cluster": sorted(merged),
            "between_edge_strength": round(best_between_weight, 6),
            "delta_modularity": round(best_delta, 6),
            "modularity_after_merge": round(best_q_after, 6),
        })

        clusters = [cluster for idx, cluster in enumerate(clusters) if idx not in {i, j}]
        clusters.append(merged)
        current_q = best_q_after

    clusters.sort(key=lambda group: (-len(group), sorted(group)[0]))
    return clusters, current_q, total_edge_strength, merge_history, adjacency_weight, degree


def build_initial_clusters(
    database_id: str,
    tables: List[TableMeta],
    max_query_tables: int = 5,
    target_cluster_count: int | None = None,
    db_path: Optional[Path] = None,
) -> InitialClusteringResponse:
    """Cluster tables using the paper's greedy weighted-modularity method.

    This implements the clustering objective from community detection:
        Q = Σ_i (e_ii - a_i²)
    where e_ii is the fraction of total edge strength inside cluster i and a_i
    is the fraction of all incident edge strength touching cluster i.  The
    algorithm greedily merges the pair of clusters with the largest positive
    modularity gain ΔQ and stops at the local maximum.

    Representatives are selected after clustering using the paper-exact table
    importance score computed in build_schema_graph().
    """
    graph = build_schema_graph(database_id, tables, db_path=db_path)
    node_map = {node.id: node for node in graph.nodes}
    table_names = sorted(node_map.keys())
    n = len(table_names)

    if n == 0:
        return InitialClusteringResponse(
            database_id=database_id,
            table_count=0,
            edge_count=0,
            cluster_count=0,
            target_cluster_count=0,
            recommended_query_set=[],
            clusters=[],
            clustering_method="paper_greedy_weighted_modularity",
            modularity_score=0.0,
            total_edge_strength=0.0,
            merge_count=0,
            merge_history=[],
        )

    max_query_tables = max(1, min(max_query_tables, n))

    groups, modularity_score, total_edge_strength, merge_history, adjacency_weight, degree = (
        _paper_greedy_modularity_clustering(table_names, graph.edges)
    )

    # If the graph has no FK edges, no modularity merge is possible; keep each
    # table as an independent subject group.
    edge_lookup = graph.edges
    clusters: List[SchemaCluster] = []

    for index, group in enumerate(groups, start=1):
        cluster_tables = sorted(group)
        representative = max(
            cluster_tables,
            key=lambda table_name: (
                node_map[table_name].importance_score,
                node_map[table_name].row_count or 0,
                node_map[table_name].referenced_by_count,
                table_name,
            ),
        )
        representative_score = node_map[representative].importance_score
        average_score = sum(node_map[name].importance_score for name in cluster_tables) / max(len(cluster_tables), 1)
        internal_edges = [
            edge for edge in edge_lookup
            if edge.source in group and edge.target in group
        ]
        internal_edge_score = sum(edge.score for edge in internal_edges)
        q_i, e_ii, a_i, internal_weight, incident_weight = _modularity_contribution(
            group, adjacency_weight, degree, total_edge_strength
        )
        label = _guess_cluster_label(cluster_tables)

        clusters.append(
            SchemaCluster(
                cluster_id=f"initial_cluster_{index}",
                label=label,
                table_count=len(cluster_tables),
                tables=cluster_tables,
                representative_table=representative,
                representative_score=round(representative_score, 4),
                average_importance_score=round(average_score, 4),
                internal_edge_score=round(internal_edge_score, 4),
                query_set_candidate=False,
                modularity_contribution=round(q_i, 6),
                e_ii=round(e_ii, 6),
                a_i=round(a_i, 6),
                internal_edge_weight=round(internal_weight, 6),
                incident_edge_weight=round(incident_weight, 6),
            )
        )

    # Pick top-m representatives as the automatic initial query set.
    # The clustering paper ranks communities by their modularity contribution Q_i;
    # representative importance is only a tie-breaker inside clusters with similar Q_i.
    ranked_clusters = sorted(
        clusters,
        key=lambda cluster: (
            cluster.modularity_contribution,
            cluster.representative_score,
            cluster.table_count,
            cluster.internal_edge_score,
            cluster.representative_table,
        ),
        reverse=True,
    )
    recommended = [cluster.representative_table for cluster in ranked_clusters[:max_query_tables]]
    recommended_set = set(recommended)

    clusters = [
        cluster.model_copy(update={"query_set_candidate": cluster.representative_table in recommended_set})
        for cluster in clusters
    ]
    clusters.sort(
        key=lambda cluster: (
            not cluster.query_set_candidate,
            -cluster.modularity_contribution,
            -cluster.representative_score,
            cluster.cluster_id,
        )
    )

    return InitialClusteringResponse(
        database_id=database_id,
        table_count=graph.node_count,
        edge_count=graph.edge_count,
        cluster_count=len(clusters),
        target_cluster_count=len(clusters),
        recommended_query_set=recommended,
        clusters=clusters,
        clustering_method="paper_greedy_weighted_modularity",
        modularity_score=round(modularity_score, 6),
        total_edge_strength=round(total_edge_strength, 6),
        merge_count=len(merge_history),
        merge_history=merge_history[-25:],
    )



def _importance_reason(node: GraphNode) -> str:
    parts: List[str] = []
    if node.referenced_by_count > 0:
        parts.append(f"referenced by {node.referenced_by_count} table(s)")
    if node.foreign_key_count > 0:
        parts.append(f"has {node.foreign_key_count} outgoing FK(s)")
    if node.row_count is not None:
        parts.append(f"contains {node.row_count} row(s)")
    if not parts:
        parts.append("included by schema structure")
    return "; ".join(parts)


def build_prequery_processing_summary(
    database_id: str,
    tables: List[TableMeta],
    max_query_tables: int = 5,
    target_cluster_count: int | None = None,
    top_n_tables: int = 8,
    db_path: Optional[Path] = None,
) -> PreQueryProcessingResponse:
    """Return all preprocessing results before user-edited query set selection.

    This endpoint bundles the stages that should be completed before the later
    interactive query-set summary graph: weighted schema graph construction,
    random-walk table importance, greedy initial clustering, representative
    selection, and recommended initial query set generation.
    """
    graph = build_schema_graph(database_id, tables, db_path=db_path)
    clustering = build_initial_clusters(
        database_id,
        tables,
        max_query_tables=max_query_tables,
        target_cluster_count=target_cluster_count,
        db_path=db_path,
    )

    ranked_nodes = sorted(
        graph.nodes,
        key=lambda node: (
            node.importance_score,
            node.referenced_by_count,
            node.foreign_key_count,
            node.id,
        ),
        reverse=True,
    )
    top_importance_tables = [
        TableImportanceItem(
            table=node.id,
            importance_score=round(node.importance_score, 4),
            rank=index,
            row_count=node.row_count,
            degree=node.foreign_key_count + node.referenced_by_count,
            referenced_by_count=node.referenced_by_count,
            foreign_key_count=node.foreign_key_count,
            reason=_importance_reason(node),
        )
        for index, node in enumerate(ranked_nodes[:max(1, top_n_tables)], start=1)
    ]

    if graph.edges:
        scores = [edge.score for edge in graph.edges]
        weights = [edge.weight for edge in graph.edges]
        strongest_edges = sorted(
            graph.edges,
            key=lambda edge: (edge.score, edge.source, edge.target),
            reverse=True,
        )[:5]
        edge_summary = EdgeWeightSummary(
            edge_count=len(graph.edges),
            min_score=round(min(scores), 4),
            max_score=round(max(scores), 4),
            average_score=round(sum(scores) / len(scores), 4),
            min_weight=round(min(weights), 4),
            max_weight=round(max(weights), 4),
            average_weight=round(sum(weights) / len(weights), 4),
            strongest_edges=strongest_edges,
        )
    else:
        edge_summary = EdgeWeightSummary(edge_count=0, strongest_edges=[])

    method_notes = [
        "Edge weight follows the Summary Graphs paper: column-level distances use D(X,Y)=1-I(X,Y)/H(X,Y); table-level FK weight is the sum of column-level distances along the primary-key-to-primary-key path.",
        "Table importance follows the schema summarization formula: IC(R)=log|R|+ΣH(R.A), then V_{i+1}=V_iΠ until convergence using the transfer-information matrix Π.",
        "Initial clusters are generated by the community-detection paper's weighted modularity objective Q=Σ(e_ii-a_i^2), using greedy merges with positive ΔQ.",
        "For clustering, schema-edge distance is converted to relationship strength s=1/(1+wt) because modularity requires similarity rather than distance.",
        "Each cluster representative is the member table with the highest paper-exact importance score.",
        "The recommended initial query set contains the top representatives and can be edited by the user in the next stage.",
    ]

    return PreQueryProcessingResponse(
        database_id=database_id,
        table_count=graph.node_count,
        edge_count=graph.edge_count,
        target_cluster_count=clustering.target_cluster_count,
        recommended_query_set=clustering.recommended_query_set,
        top_importance_tables=top_importance_tables,
        edge_weight_summary=edge_summary,
        clusters=clustering.clusters,
        method_notes=method_notes,
    )

def get_referenced_by_edges(database_id: str, table_name: str, tables: List[TableMeta], db_path: Optional[Path] = None) -> List[GraphEdge]:
    graph = build_schema_graph(database_id, tables, db_path=db_path)
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
    db_path: Optional[Path] = None,
) -> FocusGraphResponse:
    graph = build_schema_graph(database_id, tables, db_path=db_path)
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
    node_map = {node.id: node for node in graph.nodes}
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
        representative = max(
            cluster_tables,
            key=lambda table_name: node_map.get(table_name, GraphNode(id=table_name, label=table_name)).importance_score,
        )
        representative_score = node_map.get(representative, GraphNode(id=representative, label=representative)).importance_score
        average_score = sum(node_map[name].importance_score for name in cluster_tables if name in node_map) / max(len(cluster_tables), 1)

        summary_nodes.append(
            GraphNode(
                id=cluster_id,
                label=label,
                node_type="summary",
                table_count=len(cluster_tables),
                tables=cluster_tables,
                description=f"Collapsed subgraph containing {len(cluster_tables)} table(s). Representative table: {representative}.",
                importance_score=round(representative_score, 4),
                representative_table=representative,
                score_breakdown={
                    "representative_score": round(representative_score, 4),
                    "average_member_score": round(average_score, 4),
                },
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
        avg_score = sum(edge.score for edge in hidden_edges) / max(len(hidden_edges), 1)
        compressed_edges.append(
            GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                edge_type="summary_edge",
                label=f"{len(hidden_edges)} hidden relationship(s)",
                hidden_edge_count=len(hidden_edges),
                hidden_edges=labels,
                score=round(avg_score, 4),
                weight=round(1.0 / (avg_score + 1e-6), 4),
                score_breakdown={"average_hidden_edge_score": round(avg_score, 4)},
            )
        )
        existing.add(edge_id)

    return compressed_edges


def build_focus_summary_graph(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    depth: int = 1,
    db_path: Optional[Path] = None,
) -> FocusSummaryGraphResponse:
    graph = build_schema_graph(database_id, tables, db_path=db_path)
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
    db_path: Optional[Path] = None,
) -> ClusterExpandResponse:
    graph = build_schema_graph(database_id, tables, db_path=db_path)
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


def expand_summary_node_hierarchical(
    database_id: str,
    tables: List[TableMeta],
    cluster_id: str,
    member_tables: List[str],
    visible_table_ids: List[str],
    direct_expand_threshold: int = 4,
    db_path: Optional[Path] = None,
) -> ClusterExpandResponse:
    """Expand a project summary node into the next hierarchy level.

    This is used by query-aware summary nodes and later child summary nodes.
    The clicked summary node already carries its hidden member tables in
    GraphNode.tables, so this function does not need to reconstruct the original
    top-level query summary graph.

    Expansion rule:
      1. show the member table with the highest paper importance as a real node;
      2. if the remaining members are small, show them directly;
      3. otherwise, run the paper greedy modularity clustering on the remaining
         members and convert each multi-table community into a child summary node.

    Original FK edges are shown whenever both endpoints are visible.  FK edges
    touching still-collapsed child communities are represented as summary edges.
    """
    graph = build_schema_graph(database_id, tables, db_path=db_path)
    node_map = {node.id: node for node in graph.nodes}

    cluster_tables = {table_id for table_id in member_tables if table_id in node_map}
    if not cluster_tables:
        raise KeyError(f"Summary node has no valid member tables: {cluster_id}")

    visible_ids = {table_id for table_id in visible_table_ids if table_id in node_map}

    representative = max(
        cluster_tables,
        key=lambda table_name: (
            node_map[table_name].importance_score,
            node_map[table_name].referenced_by_count,
            node_map[table_name].row_count or 0,
            table_name,
        ),
    )

    remaining = set(cluster_tables) - {representative}
    direct_table_ids: Set[str] = {representative}
    child_cluster_map: Dict[str, Set[str]] = {}
    child_summary_nodes: List[GraphNode] = []

    if len(remaining) <= max(0, direct_expand_threshold - 1):
        direct_table_ids.update(remaining)
    elif remaining:
        groups, _, _, _, _, _ = _paper_greedy_modularity_clustering(sorted(remaining), graph.edges)

        for index, group in enumerate(groups, start=1):
            group = set(group)
            if len(group) <= 1:
                direct_table_ids.update(group)
                continue

            child_id = f"{cluster_id}__child_{index}"
            child_tables = sorted(group)
            child_representative = max(
                child_tables,
                key=lambda table_name: (
                    node_map[table_name].importance_score,
                    node_map[table_name].referenced_by_count,
                    node_map[table_name].row_count or 0,
                    table_name,
                ),
            )
            child_rep_score = node_map[child_representative].importance_score
            average_score = sum(node_map[name].importance_score for name in child_tables) / max(len(child_tables), 1)
            label = _guess_cluster_label(child_tables)

            child_cluster_map[child_id] = set(child_tables)
            child_summary_nodes.append(
                GraphNode(
                    id=child_id,
                    label=label,
                    node_type="summary",
                    table_count=len(child_tables),
                    tables=child_tables,
                    description=(
                        f"Child summary node created by expanding {cluster_id}. "
                        f"Representative table: {child_representative}."
                    ),
                    importance_score=round(child_rep_score, 4),
                    representative_table=child_representative,
                    score_breakdown={
                        "representative_score": round(child_rep_score, 4),
                        "average_member_score": round(average_score, 4),
                    },
                )
            )

    direct_nodes = [node_map[node_id] for node_id in sorted(direct_table_ids)]

    # Show original FK edges when both endpoints are already visible after this
    # expansion.  Then add compressed edges from visible nodes to child summaries,
    # and between child summaries when their hidden members are connected.
    expanded_visible_ids = visible_ids | direct_table_ids
    edges = _build_query_summary_edges(expanded_visible_ids, child_cluster_map, graph)

    return ClusterExpandResponse(
        database_id=database_id,
        cluster_id=cluster_id,
        nodes=direct_nodes + child_summary_nodes,
        edges=edges,
    )


def get_cluster_metadata(
    database_id: str,
    tables: List[TableMeta],
    focus_table: str,
    cluster_id: str,
    depth: int = 1,
    db_path: Optional[Path] = None,
) -> Tuple[List[TableMeta], List[GraphEdge]]:
    """Return the TableMeta list and relevant edges for a summary cluster.

    This is used by LLM summary generation. It intentionally shares the same
    clustering logic as focus-summary and expand_cluster, so the summary always
    describes the exact cluster represented by the clicked summary node.
    """
    graph = build_schema_graph(database_id, tables, db_path=db_path)
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



def _shortest_weighted_path(
    source: str,
    target: str,
    edges: List[GraphEdge],
    table_ids: Set[str],
) -> Tuple[List[str], float]:
    """Dijkstra path over the undirected schema graph using paper-inspired edge weights."""
    if source == target:
        return [source], 0.0

    adjacency: Dict[str, List[Tuple[str, float]]] = {table_id: [] for table_id in table_ids}
    for edge in edges:
        weight = max(float(edge.weight or 1.0), 1e-6)
        adjacency.setdefault(edge.source, []).append((edge.target, weight))
        adjacency.setdefault(edge.target, []).append((edge.source, weight))

    unvisited = set(table_ids)
    distance = {table_id: math.inf for table_id in table_ids}
    previous: Dict[str, str | None] = {table_id: None for table_id in table_ids}
    distance[source] = 0.0

    while unvisited:
        current = min(unvisited, key=lambda table_id: distance[table_id])
        if math.isinf(distance[current]) or current == target:
            break
        unvisited.remove(current)

        for neighbor, weight in adjacency.get(current, []):
            if neighbor not in unvisited:
                continue
            new_distance = distance[current] + weight
            if new_distance < distance[neighbor]:
                distance[neighbor] = new_distance
                previous[neighbor] = current

    if math.isinf(distance[target]):
        return [], math.inf

    path = []
    current: str | None = target
    while current is not None:
        path.append(current)
        current = previous[current]
    path.reverse()
    return path, distance[target]




def _edge_key(a: str, b: str) -> Tuple[str, str]:
    return tuple(sorted((a, b)))


def _edge_lookup_by_pair(edges: List[GraphEdge]) -> Dict[Tuple[str, str], GraphEdge]:
    lookup: Dict[Tuple[str, str], GraphEdge] = {}
    for edge in edges:
        key = _edge_key(edge.source, edge.target)
        current = lookup.get(key)
        if current is None or edge.score > current.score:
            lookup[key] = edge
    return lookup


def _path_edge_items(path: List[str], graph: SchemaGraphResponse) -> List[QueryPathEdgeItem]:
    lookup = _edge_lookup_by_pair(graph.edges)
    items: List[QueryPathEdgeItem] = []
    for source, target in zip(path, path[1:]):
        edge = lookup.get(_edge_key(source, target))
        if edge is None:
            continue
        items.append(
            QueryPathEdgeItem(
                source=edge.source,
                target=edge.target,
                edge_id=edge.id,
                label=edge.label,
                score=round(edge.score, 4),
                weight=round(edge.weight, 4),
            )
        )
    return items

def _choose_neighbor_context(
    visible_ids: Set[str],
    graph: SchemaGraphResponse,
    node_budget: int,
) -> Set[str]:
    """Add high-value one-hop context nodes while budget remains."""
    if len(visible_ids) >= node_budget:
        return set()

    node_map = {node.id: node for node in graph.nodes}
    candidates: Dict[str, float] = defaultdict(float)

    for edge in graph.edges:
        if edge.source in visible_ids and edge.target not in visible_ids:
            candidates[edge.target] = max(
                candidates[edge.target],
                0.65 * float(edge.score or 0.0) + 0.35 * node_map[edge.target].importance_score,
            )
        elif edge.target in visible_ids and edge.source not in visible_ids:
            candidates[edge.source] = max(
                candidates[edge.source],
                0.65 * float(edge.score or 0.0) + 0.35 * node_map[edge.source].importance_score,
            )

    remaining_slots = max(0, node_budget - len(visible_ids))
    ranked = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
    return {table_id for table_id, _ in ranked[:remaining_slots]}


def _assign_hidden_tables_to_anchors(
    hidden_ids: Set[str],
    visible_ids: Set[str],
    graph: SchemaGraphResponse,
) -> Dict[str, Set[str]]:
    """Greedily assign every hidden table to the closest visible anchor node."""
    if not hidden_ids or not visible_ids:
        return {}

    table_ids = {node.id for node in graph.nodes}
    anchor_map: Dict[str, Set[str]] = defaultdict(set)

    for hidden_id in sorted(hidden_ids):
        best_anchor = None
        best_distance = math.inf
        for anchor_id in visible_ids:
            _, distance = _shortest_weighted_path(hidden_id, anchor_id, graph.edges, table_ids)
            if distance < best_distance:
                best_distance = distance
                best_anchor = anchor_id

        if best_anchor is None or math.isinf(best_distance):
            # FK-less isolated table: attach it to the most important visible anchor for coverage.
            node_map = {node.id: node for node in graph.nodes}
            best_anchor = max(visible_ids, key=lambda node_id: (node_map[node_id].importance_score, node_id))
        anchor_map[best_anchor].add(hidden_id)

    return dict(anchor_map)


def _build_anchor_summary_nodes(
    hidden_ids: Set[str],
    visible_ids: Set[str],
    graph: SchemaGraphResponse,
) -> Tuple[List[GraphNode], Dict[str, Set[str]], Dict[str, str]]:
    """Build query-summary nodes by assigning hidden tables to visible anchors."""
    node_map = {node.id: node for node in graph.nodes}
    anchor_groups = _assign_hidden_tables_to_anchors(hidden_ids, visible_ids, graph)
    summary_nodes: List[GraphNode] = []
    cluster_map: Dict[str, Set[str]] = {}
    anchor_by_cluster: Dict[str, str] = {}

    for index, (anchor_id, tables_for_anchor) in enumerate(
        sorted(anchor_groups.items(), key=lambda item: (-len(item[1]), item[0])),
        start=1,
    ):
        cluster_id = f"qsummary_{index}"
        cluster_tables = sorted(tables_for_anchor)
        representative = max(
            cluster_tables,
            key=lambda table_name: (
                node_map[table_name].importance_score,
                node_map[table_name].referenced_by_count,
                table_name,
            ),
        )
        representative_score = node_map[representative].importance_score
        average_score = sum(node_map[name].importance_score for name in cluster_tables) / max(len(cluster_tables), 1)
        guessed_label = _guess_cluster_label(cluster_tables)
        label = guessed_label if not guessed_label.startswith("Schema group") else f"Context near {anchor_id}"

        cluster_map[cluster_id] = set(cluster_tables)
        anchor_by_cluster[cluster_id] = anchor_id
        summary_nodes.append(
            GraphNode(
                id=cluster_id,
                label=label,
                node_type="summary",
                table_count=len(cluster_tables),
                tables=cluster_tables,
                description=(
                    f"Collapsed context assigned to visible anchor '{anchor_id}'. "
                    f"Representative table: {representative}."
                ),
                importance_score=round(representative_score, 4),
                representative_table=representative,
                score_breakdown={
                    "representative_score": round(representative_score, 4),
                    "average_member_score": round(average_score, 4),
                },
            )
        )

    return summary_nodes, cluster_map, anchor_by_cluster


def _build_query_summary_edges(
    visible_ids: Set[str],
    cluster_map: Dict[str, Set[str]],
    graph: SchemaGraphResponse,
) -> List[GraphEdge]:
    """Return original visible edges plus compressed boundary edges."""
    visible_edges = [
        edge for edge in graph.edges
        if edge.source in visible_ids and edge.target in visible_ids
    ]
    compressed_edges = _build_compressed_edges(visible_ids, cluster_map, visible_edges, graph)

    # Also show summary-to-summary relationships if two collapsed groups are connected.
    table_to_cluster: Dict[str, str] = {}
    for cluster_id, cluster_tables in cluster_map.items():
        for table_id in cluster_tables:
            table_to_cluster[table_id] = cluster_id

    existing = {edge.id for edge in compressed_edges}
    buckets: Dict[Tuple[str, str], List[GraphEdge]] = defaultdict(list)

    for edge in graph.edges:
        source_cluster = table_to_cluster.get(edge.source)
        target_cluster = table_to_cluster.get(edge.target)
        if source_cluster and target_cluster and source_cluster != target_cluster:
            key = tuple(sorted([source_cluster, target_cluster]))
            buckets[key].append(edge)

    for (source, target), hidden_edges in buckets.items():
        edge_id = f"summary_edge__{source}__to__{target}"
        if edge_id in existing:
            continue
        avg_score = sum(edge.score for edge in hidden_edges) / max(len(hidden_edges), 1)
        compressed_edges.append(
            GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                edge_type="summary_edge",
                label=f"{len(hidden_edges)} collapsed relationship(s)",
                hidden_edge_count=len(hidden_edges),
                hidden_edges=[edge.label for edge in hidden_edges],
                score=round(avg_score, 4),
                weight=round(1.0 / (avg_score + 1e-6), 4),
                score_breakdown={"average_hidden_edge_score": round(avg_score, 4)},
            )
        )
        existing.add(edge_id)

    return compressed_edges




def _query_shortest_path_union(
    query_tables: List[str],
    graph: SchemaGraphResponse,
) -> Tuple[Set[str], List[QueryPathItem], Dict[Tuple[str, str], List[str]]]:
    """Return P, the union of shortest paths among query table pairs.

    This is the preprocessing stage used by the original Summary Graphs paper:
    the IP is solved on the union of query shortest paths rather than on the
    whole schema graph.
    """
    table_ids = {node.id for node in graph.nodes}
    path_union: Set[str] = set(query_tables)
    query_paths: List[QueryPathItem] = []
    path_by_pair: Dict[Tuple[str, str], List[str]] = {}

    for i, source in enumerate(query_tables):
        for target in query_tables[i + 1:]:
            path, total_weight = _shortest_weighted_path(source, target, graph.edges, table_ids)
            if not path:
                continue
            path_union.update(path)
            path_by_pair[(source, target)] = path
            path_edges = _path_edge_items(path, graph)
            average_score = (
                sum(edge.score for edge in path_edges) / len(path_edges)
                if path_edges
                else 0.0
            )
            query_paths.append(
                QueryPathItem(
                    source=source,
                    target=target,
                    path=path,
                    path_edges=path_edges,
                    total_weight=round(total_weight, 4),
                    average_edge_score=round(average_score, 4),
                    edge_count=max(len(path) - 1, 0),
                )
            )

    return path_union, query_paths, path_by_pair


def _path_prefix_distances(path: List[str], graph: SchemaGraphResponse) -> Dict[Tuple[str, str], float]:
    """Distance wt(u,v) for metaedges whose endpoints are on the same path."""
    lookup = _edge_lookup_by_pair(graph.edges)
    prefix = [0.0]
    for source, target in zip(path, path[1:]):
        edge = lookup.get(_edge_key(source, target))
        prefix.append(prefix[-1] + (float(edge.weight) if edge else 1.0))

    distances: Dict[Tuple[str, str], float] = {}
    for i, source in enumerate(path):
        for j in range(i + 1, len(path)):
            target = path[j]
            distances[(source, target)] = max(0.0, prefix[j] - prefix[i])
            distances[(target, source)] = max(0.0, prefix[j] - prefix[i])
    return distances


def _paper_summary_edges_for_selected_nodes(
    selected_nodes: Set[str],
    path_by_pair: Dict[Tuple[str, str], List[str]],
    graph: SchemaGraphResponse,
) -> Tuple[List[GraphEdge], float]:
    """Construct order-preserving metaedges for a fixed selected node set.

    For each query-pair shortest path, we keep the selected nodes that appear
    on that path and connect consecutive selected nodes with one metaedge.  This
    preserves the order of the original shortest path and keeps the query-pair
    distance equal to the original shortest distance because the metaedge weight
    is the sum of original edge weights along the compressed segment.
    """
    metaedge_weights: Dict[Tuple[str, str], float] = {}
    metaedge_segments: Dict[Tuple[str, str], List[str]] = {}

    for _pair, path in path_by_pair.items():
        if len(path) < 2:
            continue
        path_distances = _path_prefix_distances(path, graph)
        selected_on_path = [node for node in path if node in selected_nodes]
        if len(selected_on_path) < 2:
            continue
        for source, target in zip(selected_on_path, selected_on_path[1:]):
            key = _edge_key(source, target)
            # Recover original segment between endpoints for explanation.
            i = path.index(source)
            j = path.index(target)
            if i > j:
                i, j = j, i
            segment = path[i:j + 1]
            weight = path_distances.get((source, target), math.inf)
            current = metaedge_weights.get(key)
            if current is None or weight < current:
                metaedge_weights[key] = weight
                metaedge_segments[key] = segment

    edges: List[GraphEdge] = []
    total_weight = 0.0
    for index, ((source, target), weight) in enumerate(
        sorted(metaedge_weights.items(), key=lambda item: (item[0][0], item[0][1])),
        start=1,
    ):
        segment = metaedge_segments[(source, target)]
        hidden_tables = [node for node in segment[1:-1] if node not in {source, target}]
        score = 1.0 / (1.0 + max(weight, 0.0))
        edge_id = f"metaedge__{source}__to__{target}__{index}"
        if len(segment) == 2:
            # It is still represented as a metaedge so the output exactly
            # follows the paper's summary graph layer.
            label = f"metaedge wt={weight:.2f}"
        else:
            label = f"metaedge over {len(segment) - 1} hop(s)"
        edges.append(
            GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                edge_type="metaedge",
                label=label,
                hidden_edge_count=max(len(segment) - 1, 1),
                hidden_edges=[" → ".join(segment)],
                score=round(score, 4),
                weight=round(weight, 6),
                score_breakdown={
                    "paper_metaedge_weight": round(weight, 6),
                    "paper_metaedge_path": " → ".join(segment),
                    "compressed_intermediate_table_count": float(len(hidden_tables)),
                    "compressed_intermediate_tables": hidden_tables,
                    "paper_role": "order-preserving metaedge over query shortest path",
                },
            )
        )
        total_weight += weight

    return edges, total_weight


def _paper_original_summary_selection(
    query_tables: List[str],
    graph: SchemaGraphResponse,
    node_budget: int,
    max_exact_candidates: int = 18,
) -> Tuple[Set[str], List[GraphEdge], List[QueryPathItem], Dict[str, Any]]:
    """Select the original paper-style summary graph.

    The paper formulates this as an IP over nodes y_u and metaedges x_uv on P,
    the union of shortest paths between query tables.  To avoid adding a solver
    dependency, this implementation solves the same selection problem by exact
    enumeration when the candidate set is small enough.  For larger P, it uses a
    deterministic bounded enumeration over the most important candidates.

    We interpret the UI `node_budget` as the total visible table budget.  The
    paper's B is therefore `node_budget - |Q|` extra budget nodes.
    """
    query_set = set(query_tables)
    path_union, query_paths, path_by_pair = _query_shortest_path_union(query_tables, graph)
    node_map = {node.id: node for node in graph.nodes}

    if len(query_tables) == 1:
        return query_set, [], query_paths, {
            "paper_candidate_node_count": len(query_set),
            "paper_path_union_node_count": len(query_set),
            "paper_extra_budget": max(0, node_budget - len(query_set)),
            "paper_summary_objective_weight": 0.0,
            "paper_solver_mode": "single_query_table_no_metaedges",
            "paper_selected_budget_nodes": [],
        }

    extra_budget = max(0, node_budget - len(query_set))
    candidates = sorted(path_union - query_set)
    solver_mode = "exact_enumeration"

    # If P is large, retain the most important/path-central candidates for a
    # bounded exact search.  This is the only approximation in this stage.
    if len(candidates) > max_exact_candidates:
        occurrence = Counter()
        for path in path_by_pair.values():
            for node in path:
                if node not in query_set:
                    occurrence[node] += 1
        candidates = sorted(
            candidates,
            key=lambda node: (
                -occurrence[node],
                -node_map.get(node, GraphNode(id=node, label=node)).importance_score,
                node,
            ),
        )[:max_exact_candidates]
        solver_mode = "bounded_exact_enumeration_candidate_pruned"

    best_selected: Set[str] = set(query_set)
    best_edges: List[GraphEdge] = []
    best_weight = math.inf
    best_budget_nodes: List[str] = []

    max_r = min(extra_budget, len(candidates))
    for r in range(max_r + 1):
        for subset in itertools.combinations(candidates, r):
            selected = query_set | set(subset)
            metaedges, objective_weight = _paper_summary_edges_for_selected_nodes(selected, path_by_pair, graph)
            if not metaedges and len(query_tables) > 1:
                continue
            # Tie-break: lower objective, then fewer selected budget nodes, then
            # higher total importance, then stable lexical order.
            total_importance = sum(node_map[node].importance_score for node in selected if node in node_map)
            best_total_importance = sum(node_map[node].importance_score for node in best_selected if node in node_map)
            tie = (
                objective_weight,
                len(subset),
                -total_importance,
                tuple(sorted(subset)),
            )
            best_tie = (
                best_weight,
                len(best_budget_nodes),
                -best_total_importance,
                tuple(sorted(best_budget_nodes)),
            )
            if tie < best_tie:
                best_selected = selected
                best_edges = metaedges
                best_weight = objective_weight
                best_budget_nodes = list(subset)

    if math.isinf(best_weight):
        best_weight = 0.0

    diagnostics = {
        "paper_candidate_node_count": len(candidates),
        "paper_path_union_node_count": len(path_union),
        "paper_extra_budget": extra_budget,
        "paper_summary_objective_weight": round(best_weight, 6),
        "paper_solver_mode": solver_mode,
        "paper_selected_budget_nodes": sorted(best_selected - query_set),
        "paper_metaedge_count": len(best_edges),
    }
    return best_selected, best_edges, query_paths, diagnostics


def build_query_summary_graph(
    database_id: str,
    tables: List[TableMeta],
    query_tables: List[str],
    node_budget: int = 12,
    include_neighbors: bool = True,
    max_query_tables: int = 8,
    db_path: Optional[Path] = None,
) -> QuerySummaryGraphResponse:
    """Generate the query-aware summary graph using the original paper stage.

    Stage 1 now follows the original Summary Graphs formulation more closely:
      1. compute P, the union of weighted shortest paths between query tables;
      2. select query nodes plus at most B budget nodes from P;
      3. connect selected nodes with order-preserving metaedges;
      4. minimize the total metaedge weight.

    In the paper this is solved as an IP.  Here we solve the same discrete
    selection exactly by enumeration for small P, and use bounded enumeration
    when P is large so the prototype does not require an external IP solver.

    Stage 2 is our project extension: every table not selected by the original
    summary graph stage is collapsed into nearest-anchor summary nodes.
    """
    graph = build_schema_graph(database_id, tables, db_path=db_path)
    node_map = {node.id: node for node in graph.nodes}
    table_ids = set(node_map.keys())

    cleaned_query_tables: List[str] = []
    for table_name in query_tables:
        if table_name not in table_ids:
            raise KeyError(f"Query table not found: {table_name}")
        if table_name not in cleaned_query_tables:
            cleaned_query_tables.append(table_name)

    if not cleaned_query_tables:
        raise KeyError("Query set is empty. Add at least one table before generating a summary graph.")

    if len(cleaned_query_tables) > max_query_tables:
        raise KeyError(f"Query set is too large. Maximum allowed query tables: {max_query_tables}")

    requested_budget = max(1, node_budget)
    node_budget = max(requested_budget, len(cleaned_query_tables))
    query_set = set(cleaned_query_tables)

    selected_ids, metaedges, paths, paper_diagnostics = _paper_original_summary_selection(
        query_tables=cleaned_query_tables,
        graph=graph,
        node_budget=node_budget,
    )

    # In the original paper, selected non-query tables are the budget nodes.
    bridge_ids = selected_ids - query_set
    context_ids: Set[str] = set()

    # Optional context is now deliberately disabled for the paper-exact stage.
    # It can be added later as a separate extension, but the visible graph
    # returned here should correspond to query nodes + budget nodes only.
    visible_ids: Set[str] = set(selected_ids)
    budget_respected = len(visible_ids) <= node_budget
    hidden_ids = table_ids - visible_ids

    nodes: List[GraphNode] = []
    for node_id in sorted(visible_ids):
        node = node_map[node_id]
        if node_id in query_set:
            node = node.model_copy(update={"node_type": "query"})
        elif node_id in bridge_ids:
            node = node.model_copy(update={"node_type": "bridge"})
        nodes.append(node)

    summary_nodes, cluster_map, _anchor_by_cluster = _build_anchor_summary_nodes(hidden_ids, visible_ids, graph)

    # The original paper summary graph contains metaedges, not necessarily the
    # original FK edges.  Our extension adds compressed summary boundary edges.
    compressed_boundary_edges = _build_compressed_edges(visible_ids, cluster_map, [], graph)
    edges = metaedges + compressed_boundary_edges
    all_nodes = nodes + summary_nodes

    original_node_count = graph.node_count
    original_edge_count = graph.edge_count
    compressed_edge_count = sum(1 for edge in edges if edge.edge_type == "summary_edge")
    node_reduction = 0.0 if original_node_count == 0 else 1.0 - (len(all_nodes) / original_node_count)
    edge_reduction = 0.0 if original_edge_count == 0 else 1.0 - (len(edges) / original_edge_count)

    method_notes = [
        "Original paper stage: compute weighted shortest paths between every query-table pair and take their union P.",
        "Original paper stage: choose query nodes plus budget nodes from P and connect them with order-preserving metaedges.",
        "The optimization objective minimizes the total metaedge weight; lower weight means a more informative schema connection.",
        "The UI node budget is interpreted as |Q|+B, where B is the paper's extra budget-node limit.",
        "This prototype solves the paper IP by exact enumeration on small P; when P is large, it prunes candidate budget nodes and then enumerates exactly over the bounded candidate set.",
        "Project extension: every non-selected table is assigned to the nearest selected visible anchor and represented by an expandable summary node.",
        "Project extension: compressed summary edges are shown in addition to paper metaedges so users know where hidden schema regions attach.",
    ]

    return QuerySummaryGraphResponse(
        database_id=database_id,
        query_tables=cleaned_query_tables,
        node_budget=node_budget,
        actual_visible_table_count=len(visible_ids),
        query_node_count=len(query_set),
        bridge_node_count=len(bridge_ids),
        context_node_count=len(context_ids),
        summary_node_count=len(summary_nodes),
        hidden_node_count=len(hidden_ids),
        visible_table_ids=sorted(visible_ids),
        bridge_table_ids=sorted(bridge_ids),
        context_table_ids=sorted(context_ids),
        nodes=all_nodes,
        edges=edges,
        paths=paths,
        stats=QuerySummaryStats(
            original_node_count=original_node_count,
            original_edge_count=original_edge_count,
            query_node_count=len(query_set),
            bridge_node_count=len(bridge_ids),
            context_node_count=len(context_ids),
            visible_table_count=len(visible_ids),
            summary_node_count=len(summary_nodes),
            hidden_table_count=len(hidden_ids),
            compressed_edge_count=compressed_edge_count,
            budget_requested=requested_budget,
            budget_respected=budget_respected,
            node_reduction_ratio=round(node_reduction, 4),
            edge_reduction_ratio=round(edge_reduction, 4),
        ),
        method_spec=QuerySummaryMethodSpec(
            edge_weighting="paper-exact MI column-level path distance: wt(R,S)=min sum D(Ci,Cj), D=1-I/H",
            visible_graph_selection="original Summary Graphs IP-style stage: query nodes + budget nodes + order-preserving metaedges over query shortest-path union",
            hidden_compression="project extension: non-selected tables are assigned to nearest visible anchors and collapsed into expandable summary nodes",
        ),
        method_notes=method_notes + [
            f"paper_solver_mode={paper_diagnostics.get('paper_solver_mode')}",
            f"paper_path_union_node_count={paper_diagnostics.get('paper_path_union_node_count')}",
            f"paper_candidate_node_count={paper_diagnostics.get('paper_candidate_node_count')}",
            f"paper_extra_budget={paper_diagnostics.get('paper_extra_budget')}",
            f"paper_summary_objective_weight={paper_diagnostics.get('paper_summary_objective_weight')}",
            f"paper_selected_budget_nodes={', '.join(paper_diagnostics.get('paper_selected_budget_nodes', []))}",
        ],
    )
