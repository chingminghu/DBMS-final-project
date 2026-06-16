import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import './styles.css';

cytoscape.use(dagre);

const API_BASE = 'http://127.0.0.1:8000';

const cyStylesheet = [
  {
    selector: 'node',
    style: {
      shape: 'ellipse',
      width: 'mapData(importance_score, 0, 1, 230, 345)',
      height: 'mapData(importance_score, 0, 1, 125, 185)', 
      'background-color': '#ffffff',
      'border-width': 'mapData(importance_score, 0, 1, 2, 5)',
      'border-color': '#64748b',
      label: 'data(displayLabel)',
      color: '#0f172a',
      'font-size': 21,
      'font-weight': 900,
      'text-wrap': 'wrap',
      'text-max-width': 230,
      'text-valign': 'center',
      'text-halign': 'center',
      'line-height': 1.25,
      'text-outline-width': 2,
      'text-outline-color': '#ffffff',
      'text-outline-opacity': 0.9,
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.72,
      'text-background-padding': 5,
      'text-background-shape': 'roundrectangle',
      'min-zoomed-font-size': 0,
      'overlay-opacity': 0
    }
  },
  {
    selector: 'node[node_type = "focus"]',
    style: {
      'border-width': 3,
      'border-color': '#2563eb',
      'background-color': '#eff6ff'
    }
  },

  {
    selector: 'node.query-node, node[node_type = "query"]',
    style: {
      'border-width': 5,
      'border-color': '#7c3aed',
      'background-color': '#f5f3ff',
      color: '#4c1d95',
      'font-size': 22,
      'text-background-opacity': 0.8,
      'shadow-blur': 16,
      'shadow-color': '#7c3aed',
      'shadow-opacity': 0.28,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0
    }
  },
  {
    selector: 'node[node_type = "bridge"]',
    style: {
      'border-width': 4,
      'border-color': '#2563eb',
      'background-color': '#eff6ff',
      color: '#1e3a8a',
      'text-background-opacity': 0.8
    }
  },


  {
    selector: 'node[node_type = "summary"]',
    style: {
      width: 'mapData(importance_score, 0, 1, 285, 360)',
      height: 'mapData(importance_score, 0, 1, 145, 190)',
      'background-color': '#fff7ed',
      'border-width': 3,
      'border-style': 'dashed',
      'border-color': '#f97316',
      color: '#7c2d12',
      'font-size': 20,
      'text-max-width': 245,
      'text-background-color': '#fff7ed',
      'text-background-opacity': 0.9,
      'min-zoomed-font-size': 0
    }
  },
  {
    selector: 'node.selected-node',
    style: {
      'border-width': 5,
      'border-color': '#0f766e',
      'background-color': '#ccfbf1',
      'shadow-blur': 18,
      'shadow-color': '#14b8a6',
      'shadow-opacity': 0.38,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0
    }
  },
  {
    selector: 'node.newly-expanded',
    style: {
      // The visible green dot is now rendered as a tiny independent marker node.
      // Keep a soft glow on the expanded node as a secondary cue.
      'shadow-blur': 14,
      'shadow-color': '#22c55e',
      'shadow-opacity': 0.18,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0
    }
  },
  {
    selector: 'node[node_type = "new_marker"]',
    style: {
      shape: 'ellipse',
      width: 24,
      height: 24,
      'background-color': '#22c55e',
      'border-width': 4,
      'border-color': '#ffffff',
      label: '',
      'overlay-opacity': 0,
      'events': 'no',
      'z-index': 9999
    }
  },
  {
    selector: 'edge',
    style: {
      width: 'mapData(score, 0, 1, 1.6, 5)',
      'line-color': '#94a3b8',
      'target-arrow-color': '#94a3b8',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      label: '',
      'font-size': 13,
      color: '#334155',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.92,
      'text-background-padding': 3,
      'text-rotation': 'autorotate',
      'overlay-opacity': 0
    }
  },
  {
    selector: 'edge[edge_type = "summary_edge"]',
    style: {
      width: 'mapData(score, 0, 1, 2.2, 5.5)',
      'line-style': 'dashed',
      'line-color': '#ea580c',
      'target-arrow-color': '#ea580c',
      'arrow-scale': 1.65,
      color: '#7c2d12',
      'font-weight': 800
    }
  },
  {
    selector: 'edge[edge_type = "metaedge"]',
    style: {
      width: 'mapData(score, 0, 1, 2.0, 5.2)',
      'line-style': 'solid',
      'line-color': '#2563eb',
      'target-arrow-color': '#2563eb',
      'arrow-scale': 1.7,
      color: '#1e3a8a',
      'font-weight': 800
    }
  },
  {
    selector: 'edge:selected, edge.edge-hover, edge.inspected-edge',
    style: {
      width: 3.4,
      'line-color': '#0f766e',
      'target-arrow-color': '#0f766e',
      'arrow-scale': 1.8,
      label: 'data(displayLabel)',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.96,
      'text-background-padding': 4,
      'font-size': 13,
      'font-weight': 800
    }
  },
  {
    selector: 'edge[edge_type = "metaedge"]:selected, edge[edge_type = "metaedge"].edge-hover, edge[edge_type = "metaedge"].inspected-edge',
    style: {
      'line-color': '#0f766e',
      'target-arrow-color': '#0f766e',
      'target-arrow-shape': 'triangle',
      label: 'data(displayLabel)',
      color: '#0f766e'
    }
  }
];



function splitPathString(pathString) {
  if (!pathString || typeof pathString !== 'string') return [];
  return pathString
    .split(/\s*(?:→|->|=>)\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function extractEdgePath(edge) {
  if (!edge) return [];
  if (Array.isArray(edge.path)) return edge.path.filter(Boolean);
  if (Array.isArray(edge.original_path)) return edge.original_path.filter(Boolean);
  if (Array.isArray(edge.score_breakdown?.path)) return edge.score_breakdown.path.filter(Boolean);
  if (typeof edge.score_breakdown?.paper_metaedge_path === 'string') {
    return splitPathString(edge.score_breakdown.paper_metaedge_path);
  }
  if (Array.isArray(edge.hidden_edges) && edge.hidden_edges.length > 0) {
    return splitPathString(edge.hidden_edges[0]);
  }
  return [];
}

function formatColumnMapping(edge) {
  if (!edge) return '';
  if (edge.from_column || edge.to_column) {
    return `${edge.source}.${edge.from_column || '?'} → ${edge.target}.${edge.to_column || '?'}`;
  }
  if (edge.column_mapping) return edge.column_mapping;
  if (edge.score_breakdown?.column_mapping) return edge.score_breakdown.column_mapping;
  return '';
}

function findOriginalEdgeBetween(source, target, graph) {
  const graphEdges = graph?.edges || [];
  return graphEdges.find((edge) => edge.source === source && edge.target === target)
    || graphEdges.find((edge) => edge.source === target && edge.target === source)
    || null;
}

function buildPathColumnMappings(path, graph) {
  if (!Array.isArray(path) || path.length < 2) return [];
  const mappings = [];
  for (let i = 0; i < path.length - 1; i += 1) {
    const source = path[i];
    const target = path[i + 1];
    const originalEdge = findOriginalEdgeBetween(source, target, graph);
    mappings.push({
      source,
      target,
      label: originalEdge
        ? formatColumnMapping(originalEdge)
        : `${source} → ${target}`,
      weight: originalEdge?.weight,
      score: originalEdge?.score,
      edge_type: originalEdge?.edge_type || 'fk'
    });
  }
  return mappings;
}

function enrichEdgeDetail(edge, graph) {
  const path = extractEdgePath(edge);
  const columnMapping = formatColumnMapping(edge);
  const pathColumnMappings = edge?.edge_type === 'metaedge'
    ? buildPathColumnMappings(path, graph)
    : [];

  return {
    ...edge,
    normalized_path: path,
    column_mapping: columnMapping,
    path_column_mappings: pathColumnMappings
  };
}

function EdgeMetrics({ edge }) {
  const b = edge?.score_breakdown || {};
  const hasProfile = Number(b.profile_available || 0) >= 1;
  return (
    <div className="edge-metrics">
      <small>
        score {Number(edge?.score ?? 0).toFixed(2)} · weight {Number(edge?.weight ?? 0).toFixed(2)}
        {edge?.edge_type === 'metaedge' ? ' · paper metaedge' : ''}
      </small>
      {hasProfile ? (
        <div className="edge-metric-grid">
          <span>Schema wt</span>
          <strong>{Number(b.paper_schema_weight ?? edge?.weight ?? 0).toFixed(3)}</strong>
          <span>FK D</span>
          <strong>{Number(b.fk_to_target_distance ?? b.information_distance ?? 0).toFixed(3)}</strong>
          <span>srcPK→FK</span>
          <strong>{Number(b.source_pk_to_fk_distance ?? 0).toFixed(3)}</strong>
          <span>ref→tgtPK</span>
          <strong>{Number(b.target_ref_to_pk_distance ?? 0).toFixed(3)}</strong>
          <span>MI</span>
          <strong>{Number(b.mutual_information ?? 0).toFixed(3)}</strong>
          <span>H(X,Y)</span>
          <strong>{Number(b.joint_entropy ?? 0).toFixed(3)}</strong>
          <span>Sample</span>
          <strong>{Number(b.sample_size ?? 0).toFixed(0)}</strong>
        </div>
      ) : (
        <div className="edge-metric-note">metadata fallback edge weight</div>
      )}
    </div>
  );
}


function getSummaryRepresentativeName(node) {
  if (!node) return 'Summary';
  const representative = node.representative_table
    || node.anchor_table
    || node.score_breakdown?.anchor_table
    || node.score_breakdown?.representative_table
    || node.tables?.[0]
    || node.member_tables?.[0]
    || node.label
    || 'Summary';
  return String(representative);
}

function getSummaryTableCount(node) {
  if (!node) return 0;
  return Number(
    node.table_count
    ?? node.collapsed_count
    ?? node.tables?.length
    ?? node.member_tables?.length
    ?? 0
  );
}

function formatSummaryNodeLabel(node) {
  const representative = getSummaryRepresentativeName(node);
  const count = getSummaryTableCount(node);
  return `${representative} Module\n${count} tables`;
}

const layoutOptions = {
  name: 'dagre',
  rankDir: 'LR',
  nodeSep: 95,
  edgeSep: 35,
  rankSep: 150,
  fit: true,
  padding: 60,
  animate: true,
  animationDuration: 350
};

function graphToElements(nodesInput, edgesInput) {
  const nodes = nodesInput.map((node) => {
    const displayLabel = node.node_type === 'summary'
      ? formatSummaryNodeLabel(node)
      : node.label;

    return {
      data: {
        ...node,
        id: node.id,
        label: node.label,
        displayLabel
      },
      classes: [
        node.node_type === 'focus' ? 'focus-node' : '',
        node.node_type === 'query' ? 'query-node' : '',
        node.is_newly_expanded ? 'newly-expanded' : ''
      ].filter(Boolean).join(' ')
    };
  });

  const edges = edgesInput.map((edge) => {
    const path = extractEdgePath(edge);
    const hopCount = Math.max(path.length - 1, Number(edge.hidden_edge_count || 0));
    const fkMapping = formatColumnMapping(edge) || `${edge.from_column || '?'} → ${edge.to_column || '?'}`;

    return {
      data: {
        ...edge,
        id: edge.id,
        source: edge.source,
        target: edge.target,
        normalized_path: path,
        label: edge.edge_type === 'summary_edge' || edge.edge_type === 'metaedge'
          ? edge.label
          : fkMapping,
        displayLabel: edge.edge_type === 'summary_edge'
          ? `${edge.label}
score ${Number(edge.score ?? 0).toFixed(2)}`
          : edge.edge_type === 'metaedge'
            ? `metaedge${hopCount > 0 ? ` · ${hopCount} hop(s)` : ''}
wt ${Number(edge.weight ?? 0).toFixed(2)}`
            : fkMapping
      },
      classes: ''
    };
  });

  return [...nodes, ...edges];
}

function App() {
  const cyRef = useRef(null);
  const tableDetailCacheRef = useRef(new Map());
  const prefetchingTablesRef = useRef(new Set());
  const skipNextAutoLayoutRef = useRef(false);
  const selectedNodeIdRef = useRef('');

  const [savedDatabases, setSavedDatabases] = useState([]);
  const [savedDatabaseId, setSavedDatabaseId] = useState('');
  const [databaseInfo, setDatabaseInfo] = useState(null);
  const [fullGraph, setFullGraph] = useState(null);
  const [initialClusters, setInitialClusters] = useState(null);
  const [preQueryInfo, setPreQueryInfo] = useState(null);
  const [preQueryProgress, setPreQueryProgress] = useState({
    active: false,
    stage: 'Waiting to start',
    elapsedSeconds: 0,
    error: ''
  });
  const [querySet, setQuerySet] = useState([]);
  const [nodeBudget, setNodeBudget] = useState(12);
  const [querySummaryInfo, setQuerySummaryInfo] = useState(null);
  const [focusInfo, setFocusInfo] = useState(null);
  const [viewMode, setViewMode] = useState('full');
  const [focusDepth, setFocusDepth] = useState(1);
  const [elements, setElements] = useState([]);
  const [graphHistory, setGraphHistory] = useState([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [currentFocusTable, setCurrentFocusTable] = useState('');
  const [tableDetail, setTableDetail] = useState(null);
  const [clusterDetail, setClusterDetail] = useState(null);
  const [edgeDetail, setEdgeDetail] = useState(null);
  const [clusterSummaryLoading, setClusterSummaryLoading] = useState(false);
  const [inspectorLoadingTable, setInspectorLoadingTable] = useState('');
  const [expandingSummaryNodeId, setExpandingSummaryNodeId] = useState('');
  const [showPreQueryDetails, setShowPreQueryDetails] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('請先上傳 SQLite .db 檔案，或從已儲存的 database 選單載入。');

  const tableNames = useMemo(() => {
    if (!fullGraph) return [];
    return fullGraph.nodes.map((n) => n.id).sort();
  }, [fullGraph]);

  const captureGraphPositions = useCallback(() => {
    const cy = cyRef.current;
    const positions = new Map();

    if (!cy) return positions;

    cy.nodes().forEach((node) => {
      const position = node.position();
      positions.set(node.id(), { x: position.x, y: position.y });
    });

    return positions;
  }, []);

  const getExpansionNodePositions = useCallback((centerPosition, total, occupiedPositions = []) => {
    const safeCenter = centerPosition || { x: 0, y: 0 };
    const positions = [];
    const occupied = [
      ...occupiedPositions.filter(Boolean),
      ...positions
    ];

    // Nodes in this UI are large ellipses. A small expansion radius makes newly
    // expanded summary nodes overlap with their neighboring anchors, so we use a
    // wider ring and reject candidate positions that are too close to existing
    // visible nodes. This keeps old nodes stable while giving new nodes space.
    const minXGap = 430;
    const minYGap = 245;
    const baseRadius = 310;
    const ringGap = 235;
    const preferredAngles = [
      Math.PI / 2,
      -Math.PI / 2,
      0,
      Math.PI,
      Math.PI / 4,
      (3 * Math.PI) / 4,
      (-3 * Math.PI) / 4,
      -Math.PI / 4
    ];

    const collides = (candidate) => occupied.some((position) => {
      const dx = Math.abs(candidate.x - position.x);
      const dy = Math.abs(candidate.y - position.y);
      return dx < minXGap && dy < minYGap;
    });

    for (let index = 0; index < total; index += 1) {
      let chosen = null;

      for (let ring = 0; ring < 8 && !chosen; ring += 1) {
        const radius = baseRadius + ring * ringGap;
        const angleOffset = ring % 2 === 0 ? 0 : Math.PI / 8;
        const angleCandidates = preferredAngles.map((angle) => angle + angleOffset);

        for (const angle of angleCandidates) {
          const candidate = {
            x: safeCenter.x + Math.cos(angle) * radius,
            y: safeCenter.y + Math.sin(angle) * radius
          };

          if (!collides(candidate)) {
            chosen = candidate;
            break;
          }
        }
      }

      if (!chosen) {
        // Fallback: place nodes in a loose diagonal strip instead of stacking them.
        chosen = {
          x: safeCenter.x + baseRadius + index * 360,
          y: safeCenter.y + baseRadius + index * 190
        };
      }

      positions.push(chosen);
      occupied.push(chosen);
    }

    return positions;
  }, []);

  const getNewMarkerPosition = useCallback((nodeElement) => {
    const position = nodeElement?.position || { x: 0, y: 0 };
    const isSummary = nodeElement?.data?.node_type === 'summary';
    return {
      x: position.x + (isSummary ? 155 : 132),
      y: position.y - (isSummary ? 78 : 64)
    };
  }, []);

  const createNewExpansionMarker = useCallback((nodeElement) => ({
    data: {
      id: `__new_marker__${nodeElement.data.id}`,
      label: '',
      displayLabel: '',
      node_type: 'new_marker',
      target_node_id: nodeElement.data.id,
      importance_score: 0
    },
    classes: 'new-expansion-marker',
    grabbable: false,
    selectable: false,
    position: getNewMarkerPosition(nodeElement)
  }), [getNewMarkerPosition]);

  const syncNewExpansionMarkers = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes('[node_type = "new_marker"]').forEach((marker) => {
      const targetId = marker.data('target_node_id');
      const target = cy.getElementById(targetId);
      if (!target || target.length === 0) {
        marker.remove();
        return;
      }

      const targetPosition = target.position();
      const targetType = target.data('node_type');
      marker.position({
        x: targetPosition.x + (targetType === 'summary' ? 155 : 132),
        y: targetPosition.y - (targetType === 'summary' ? 78 : 64)
      });
    });
  }, []);


  const renderFullGraph = useCallback((graphData) => {
    setElements(graphToElements(graphData.nodes, graphData.edges));
    setFocusInfo(null);
    setClusterDetail(null);
    setEdgeDetail(null);
    setQuerySummaryInfo(null);
    setViewMode('full');
  }, []);

  const resetGraphState = useCallback(() => {
    setFullGraph(null);
    setInitialClusters(null);
    setPreQueryInfo(null);
    setPreQueryProgress({ active: false, stage: 'Waiting to start', elapsedSeconds: 0, error: '' });
    setQuerySet([]);
    setQuerySummaryInfo(null);
    setFocusInfo(null);
    setElements([]);
    setGraphHistory([]);
    setSelectedTable('');
    setCurrentFocusTable('');
    setTableDetail(null);
    setClusterDetail(null);
    setEdgeDetail(null);
    setInspectorLoadingTable('');
    setExpandingSummaryNodeId('');
    tableDetailCacheRef.current.clear();
    prefetchingTablesRef.current.clear();
  }, []);

  const fetchPreQueryProcessing = useCallback(async (databaseId) => {
    if (!databaseId) return null;

    let cancelled = false;
    const startedAt = Date.now();

    setPreQueryInfo(null);
    setPreQueryProgress({
      active: true,
      stage: 'Checking backend pre-query cache...',
      elapsedSeconds: 0,
      error: ''
    });

    const elapsedTimer = window.setInterval(() => {
      if (cancelled) return;
      setPreQueryProgress((current) => {
        if (!current.active) return current;
        return {
          ...current,
          elapsedSeconds: Math.max(1, Math.floor((Date.now() - startedAt) / 1000))
        };
      });
    }, 1000);

    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseId}/prequery?max_query_tables=5&top_n_tables=8`);
      if (!res.ok) throw new Error('Pre-query processing failed');
      const data = await res.json();
      setPreQueryInfo(data);
      setInitialClusters({
        database_id: data.database_id,
        table_count: data.table_count,
        edge_count: data.edge_count,
        cluster_count: data.clusters?.length || 0,
        target_cluster_count: data.target_cluster_count,
        recommended_query_set: data.recommended_query_set || [],
        clusters: data.clusters || []
      });
      setPreQueryProgress({
        active: false,
        stage: data.cache_hit ? 'Loaded pre-query result from backend cache' : 'Pre-query result computed and cached',
        elapsedSeconds: Math.max(0, Math.floor((Date.now() - startedAt) / 1000)),
        error: ''
      });
      return data;
    } catch (err) {
      setPreQueryInfo(null);
      setInitialClusters(null);
      setPreQueryProgress({
        active: false,
        stage: 'Pre-query processing failed',
        elapsedSeconds: Math.max(0, Math.floor((Date.now() - startedAt) / 1000)),
        error: err?.message || 'Unknown error'
      });
      return null;
    } finally {
      cancelled = true;
      window.clearInterval(elapsedTimer);
    }
  }, []);

  const loadDatabaseById = useCallback(async (databaseId) => {
    if (!databaseId) return;

    setLoading(true);
    setMessage('正在載入已儲存的 database...');
    resetGraphState();

    try {
      const infoRes = await fetch(`${API_BASE}/api/databases/${databaseId}`);
      if (!infoRes.ok) {
        const error = await infoRes.json();
        throw new Error(error.detail || 'Database load failed');
      }

      const info = await infoRes.json();
      setDatabaseInfo(info);
      setSavedDatabaseId(databaseId);

      const graphRes = await fetch(`${API_BASE}/api/databases/${databaseId}/graph`);
      if (!graphRes.ok) {
        const error = await graphRes.json();
        throw new Error(error.detail || 'Graph fetch failed');
      }

      const graphData = await graphRes.json();
      setFullGraph(graphData);
      renderFullGraph(graphData);
      fetchPreQueryProcessing(databaseId);
      setMessage(`已載入 ${info.filename}：${graphData.node_count} tables, ${graphData.edge_count} foreign keys。`);
    } catch (err) {
      setDatabaseInfo(null);
      setSavedDatabaseId('');
      setMessage(`載入 database 失敗：${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [resetGraphState, renderFullGraph, fetchPreQueryProcessing]);

  const refreshSavedDatabases = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/databases`);
      if (!res.ok) return;
      const data = await res.json();
      setSavedDatabases(data.databases || []);
    } catch (err) {
      // Keep the upload workflow available even if the database list fails.
    }
  }, []);

  useEffect(() => {
    refreshSavedDatabases();
  }, [refreshSavedDatabases]);


  const pushCurrentGraphState = useCallback(() => {
    setGraphHistory((history) => [
      ...history,
      {
        elements,
        focusInfo,
        viewMode,
        currentFocusTable,
        selectedTable,
        tableDetail,
        clusterDetail,
        edgeDetail,
        querySet,
        querySummaryInfo,
        message
      }
    ].slice(-20));
  }, [
    elements,
    focusInfo,
    viewMode,
    currentFocusTable,
    selectedTable,
    tableDetail,
    clusterDetail,
    edgeDetail,
    querySet,
    querySummaryInfo,
    message
  ]);

  const restorePreviousStep = useCallback(() => {
    if (graphHistory.length === 0) {
      setMessage('目前沒有可以回復的上一步。');
      return;
    }

    const previous = graphHistory[graphHistory.length - 1];

    setElements(previous.elements);
    setFocusInfo(previous.focusInfo);
    setViewMode(previous.viewMode);
    setCurrentFocusTable(previous.currentFocusTable);
    setSelectedTable(previous.selectedTable);
    setTableDetail(previous.tableDetail);
    setClusterDetail(previous.clusterDetail);
    setEdgeDetail(previous.edgeDetail || null);
    setQuerySet(previous.querySet || []);
    setQuerySummaryInfo(previous.querySummaryInfo || null);
    setGraphHistory((history) => history.slice(0, -1));
    setMessage('已回到上一步。');
  }, [graphHistory]);

  const clearAllNewExpandedMarkers = useCallback(() => {
    const cy = cyRef.current;

    if (cy) {
      cy.nodes('[node_type = "new_marker"]').remove();
      cy.nodes('.newly-expanded').forEach((node) => {
        node.removeClass('newly-expanded');
        node.data('is_newly_expanded', false);
      });
    }

    skipNextAutoLayoutRef.current = true;
    setElements((currentElements) => currentElements
      .filter((el) => el.data?.node_type !== 'new_marker')
      .map((el) => {
        if (!el.data?.is_newly_expanded && !String(el.classes || '').includes('newly-expanded')) {
          return el;
        }
        return {
          ...el,
          data: {
            ...el.data,
            is_newly_expanded: false
          },
          classes: String(el.classes || '')
            .split(/\s+/)
            .filter((className) => className && className !== 'newly-expanded')
            .join(' ')
        };
      })
    );
  }, []);


  const rerunLayout = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) {
      setMessage('Graph is not ready yet.');
      return;
    }

    // Marker nodes are only meant to indicate newly expanded nodes at their
    // original position. If the user rearranges the graph, remove the markers
    // instead of trying to keep them synchronized through a layout animation.
    clearAllNewExpandedMarkers();

    cy.nodes().unlock();

    const layout = cy.elements().not('[node_type = "new_marker"]').layout({
      ...layoutOptions,
      animate: true,
      animationDuration: 450,
      fit: true,
      padding: 70
    });

    layout.run();

    layout.promiseOn('layoutstop').then(() => {
      syncNewExpansionMarkers();
      cy.fit(cy.elements().not('[node_type = "new_marker"]'), 70);
      setMessage('Graph layout has been rearranged.');
    });
  }, [clearAllNewExpandedMarkers, syncNewExpansionMarkers]);

  useEffect(() => {
    if (elements.length > 0) {
      if (skipNextAutoLayoutRef.current) {
        skipNextAutoLayoutRef.current = false;
        return;
      }
      setTimeout(rerunLayout, 30);
    }
  }, [elements, rerunLayout]);

  const markSelectedNode = useCallback((nodeId) => {
    const selectedId = nodeId || '';
    selectedNodeIdRef.current = selectedId;

    const cy = cyRef.current;
    if (cy) {
      cy.nodes().removeClass('selected-node');
      if (selectedId) {
        const node = cy.getElementById(selectedId);
        if (node && node.length > 0 && node.data('node_type') !== 'new_marker') {
          node.addClass('selected-node');
        }
      }
    }

    // Cytoscape classes added imperatively can be lost after React updates the
    // elements array, which happens when clearing a green marker. Keep the
    // selected state in the element data as well so newly expanded nodes still
    // show the teal selected color after their marker disappears.
    skipNextAutoLayoutRef.current = true;
    setElements((currentElements) => currentElements.map((el) => {
      if (!el.data || el.data.source || el.data.target || el.data.node_type === 'new_marker') {
        return el;
      }

      const baseClasses = String(el.classes || '')
        .split(/\s+/)
        .filter((className) => className && className !== 'selected-node')
        .join(' ');

      if (el.data.id !== selectedId) {
        return { ...el, classes: baseClasses };
      }

      return {
        ...el,
        classes: `${baseClasses} selected-node`.trim()
      };
    }));
  }, []);

  const clearNewExpandedMarker = useCallback((nodeId) => {
    if (!nodeId) return;

    const cy = cyRef.current;
    const markerId = `__new_marker__${nodeId}`;

    if (cy) {
      const cyNode = cy.getElementById(nodeId);
      if (cyNode && cyNode.length > 0) {
        cyNode.removeClass('newly-expanded');
        cyNode.data('is_newly_expanded', false);
      }

      const markerNode = cy.getElementById(markerId);
      if (markerNode && markerNode.length > 0) {
        markerNode.remove();
      }
    }

    skipNextAutoLayoutRef.current = true;
    setElements((currentElements) => currentElements
      .filter((el) => el.data?.id !== markerId)
      .map((el) => {
        if (el.data?.id !== nodeId) return el;
        return {
          ...el,
          data: {
            ...el.data,
            is_newly_expanded: false
          },
          classes: String(el.classes || '')
            .split(/\s+/)
            .filter((className) => className && className !== 'newly-expanded')
            .join(' ')
        };
      })
    );
  }, []);





  const updateQueryNodeClasses = useCallback((nextQuerySet = querySet) => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes().removeClass('query-node');
    nextQuerySet.forEach((tableName) => {
      const node = cy.getElementById(tableName);
      if (node && node.length > 0) {
        node.addClass('query-node');
      }
    });
  }, [querySet]);

  useEffect(() => {
    updateQueryNodeClasses(querySet);
  }, [querySet, elements, updateQueryNodeClasses]);

  const addToQuerySet = useCallback((tableName) => {
    if (!tableName) return;

    setQuerySet((current) => {
      if (current.includes(tableName)) return current;
      return [...current, tableName];
    });
    setMessage(`${tableName} 已加入 Query Set。`);
  }, []);

  const removeFromQuerySet = useCallback((tableName) => {
    setQuerySet((current) => current.filter((name) => name !== tableName));
    setMessage(`${tableName} 已從 Query Set 移除。`);
  }, []);

  const toggleSelectedTableQuerySet = useCallback(() => {
    if (!selectedTable) {
      setMessage('請先選擇一張 table。');
      return;
    }

    if (querySet.includes(selectedTable)) {
      removeFromQuerySet(selectedTable);
    } else {
      addToQuerySet(selectedTable);
    }
  }, [selectedTable, querySet, addToQuerySet, removeFromQuerySet]);

  const clearQuerySet = useCallback(() => {
    setQuerySet([]);
    setMessage('已清空 Query Set。');
  }, []);

  const useRecommendedQuerySet = useCallback(() => {
    const recommended = preQueryInfo?.recommended_query_set || [];
    setQuerySet(recommended);
    setMessage(`已套用 recommended initial query set：${recommended.join(', ') || 'empty'}。`);
  }, [preQueryInfo]);

  const getTableCacheKey = useCallback((databaseId, tableName) => `${databaseId}::${tableName}`, []);

  const buildInstantTableDetail = useCallback((tableName, nodeData = null, loading = true) => ({
    table: {
      name: tableName,
      columns: nodeData?.columns || [],
      primary_keys: nodeData?.primary_keys || [],
      row_count: nodeData?.row_count ?? null
    },
    node: nodeData || null,
    outgoing_edges: [],
    referenced_by: [],
    loading
  }), []);

  const prefetchTableDetail = useCallback(async (tableName) => {
    if (!databaseInfo || !tableName) return;

    const cacheKey = getTableCacheKey(databaseInfo.database_id, tableName);
    if (tableDetailCacheRef.current.has(cacheKey) || prefetchingTablesRef.current.has(cacheKey)) return;

    prefetchingTablesRef.current.add(cacheKey);
    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/tables/${tableName}`);
      if (!res.ok) return;
      const detail = await res.json();
      tableDetailCacheRef.current.set(cacheKey, detail);
    } catch (err) {
      // Background prefetch should never interrupt graph interaction.
    } finally {
      prefetchingTablesRef.current.delete(cacheKey);
    }
  }, [databaseInfo, getTableCacheKey]);

  const fetchTableDetail = useCallback(async (tableName, nodeData = null) => {
    if (!databaseInfo || !tableName) return;

    setSelectedTable(tableName);
    setClusterDetail(null);
    setEdgeDetail(null);

    const cacheKey = getTableCacheKey(databaseInfo.database_id, tableName);
    const cachedDetail = tableDetailCacheRef.current.get(cacheKey);

    if (cachedDetail) {
      setInspectorLoadingTable('');
      setTableDetail({
        ...cachedDetail,
        node: cachedDetail.node || nodeData || null,
        loading: false
      });
      return;
    }

    setInspectorLoadingTable(tableName);

    // Open the inspector immediately so node clicks feel responsive.
    // The full column / FK metadata is filled in after the API call returns.
    setTableDetail(buildInstantTableDetail(tableName, nodeData, true));

    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/tables/${tableName}`);
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to fetch table detail');
      }
      const detail = await res.json();
      tableDetailCacheRef.current.set(cacheKey, detail);
      setTableDetail({
        ...detail,
        node: detail.node || nodeData || null,
        loading: false
      });
    } catch (err) {
      setMessage(`取得 table detail 失敗：${err.message}`);
    } finally {
      setInspectorLoadingTable((current) => current === tableName ? '' : current);
    }
  }, [databaseInfo, getTableCacheKey, buildInstantTableDetail]);

  useEffect(() => {
    if (!databaseInfo || elements.length === 0) return;

    const visibleTableNames = elements
      .filter((el) => el.data && ['query', 'bridge', 'table', 'focus'].includes(el.data.node_type))
      .map((el) => el.data.id)
      .filter(Boolean)
      .slice(0, 40);

    visibleTableNames.forEach((tableName, index) => {
      window.setTimeout(() => prefetchTableDetail(tableName), 30 * index);
    });
  }, [databaseInfo, elements, prefetchTableDetail]);

  const updateNodeLabel = useCallback((nodeId, label, summary) => {
    setElements((currentElements) =>
      currentElements.map((el) => {
        if (!el.data || el.data.id !== nodeId) return el;
        const nextDataForLabel = { ...el.data, label, llm_summary: summary };
        const displayLabel = el.data.node_type === 'summary'
          ? formatSummaryNodeLabel(nextDataForLabel)
          : label;
        return {
          ...el,
          data: {
            ...el.data,
            label,
            displayLabel,
            llm_summary: summary
          }
        };
      })
    );
  }, []);

  const refreshSummaryNodeLabels = useCallback(async (focusData, focusTableForSummary) => {
    if (!databaseInfo || !focusData) return;

    const summaryNodes = focusData.nodes.filter((node) => node.node_type === 'summary');

    for (const summaryNode of summaryNodes) {
      try {
        const res = await fetch(
          `${API_BASE}/api/databases/${databaseInfo.database_id}/clusters/${summaryNode.id}/summary?table=${encodeURIComponent(focusTableForSummary)}&depth=${focusData.depth}`
        );
        if (!res.ok) continue;

        const summary = await res.json();
        updateNodeLabel(summaryNode.id, summary.module_name_zh, summary);

        setFocusInfo((currentFocusInfo) => {
          if (!currentFocusInfo) return currentFocusInfo;
          return {
            ...currentFocusInfo,
            nodes: currentFocusInfo.nodes.map((node) =>
              node.id === summaryNode.id
                ? {
                    ...node,
                    label: summary.module_name_zh,
                    llm_summary: summary
                  }
                : node
            )
          };
        });
      } catch (err) {
        // Keep rule-based label if summary request fails.
      }
    }
  }, [databaseInfo, updateNodeLabel]);

  const renderFocusSummaryGraph = useCallback(async (tableName, depth = focusDepth) => {
    if (!databaseInfo || !tableName) return;

    setLoading(true);
    setMessage(`正在產生 ${tableName} 的 Cytoscape summary view...`);

    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/focus-summary?table=${encodeURIComponent(tableName)}&depth=${depth}`);
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Focus summary graph fetch failed');
      }

      const focusData = await res.json();

      setFocusInfo(focusData);
      setQuerySummaryInfo(null);
      setCurrentFocusTable(tableName);
      setViewMode('summary');
      setClusterDetail(null);
      setEdgeDetail(null);
      setElements(graphToElements(focusData.nodes, focusData.edges));

      refreshSummaryNodeLabels(focusData, tableName);

      setMessage(
        `Summary view：顯示 ${focusData.visible_node_count} table nodes + ${focusData.summary_node_count} summary nodes，壓縮 ${focusData.hidden_node_count} hidden tables。`
      );
    } catch (err) {
      setMessage(`Summary view 錯誤：${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [databaseInfo, focusDepth, refreshSummaryNodeLabels]);

  const generateQuerySummaryGraph = useCallback(async () => {
    if (!databaseInfo) {
      setMessage('請先載入 database。');
      return;
    }

    if (querySet.length === 0) {
      setMessage('請先至少加入一張 table 到 Query Set。');
      return;
    }

    pushCurrentGraphState();
    setLoading(true);
    setMessage('正在根據 Query Set 產生 query-aware summary graph...');

    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/query-summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query_tables: querySet,
          node_budget: nodeBudget,
          include_neighbors: true,
          max_query_tables: 8
        })
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Query summary graph failed');
      }

      const data = await res.json();
      setQuerySummaryInfo(data);
      setFocusInfo(null);
      setCurrentFocusTable('');
      setClusterDetail(null);
      setEdgeDetail(null);
      setViewMode('query-summary');
      setElements(graphToElements(data.nodes, data.edges));
      const budgetStatus = data.stats?.budget_respected === false ? '（query paths 超過 budget，已優先保留連通性）' : '';
      setMessage(`Query summary graph：${data.query_node_count} query nodes + ${data.bridge_node_count} bridge nodes + ${data.summary_node_count} summary nodes，壓縮 ${data.hidden_node_count} hidden tables。${budgetStatus}`);
    } catch (err) {
      setMessage(`Query summary graph 錯誤：${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [databaseInfo, querySet, nodeBudget, pushCurrentGraphState]);


  const handleUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setLoading(true);
    setMessage('上傳與解析中...');
    setDatabaseInfo(null);
    setSavedDatabaseId('');
    resetGraphState();

    try {
      const formData = new FormData();
      formData.append('file', file);

      const uploadRes = await fetch(`${API_BASE}/api/databases/upload`, {
        method: 'POST',
        body: formData
      });

      if (!uploadRes.ok) {
        const error = await uploadRes.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const uploaded = await uploadRes.json();
      setDatabaseInfo(uploaded);
      setSavedDatabaseId(uploaded.database_id);

      const graphRes = await fetch(`${API_BASE}/api/databases/${uploaded.database_id}/graph`);
      if (!graphRes.ok) {
        const error = await graphRes.json();
        throw new Error(error.detail || 'Graph fetch failed');
      }

      const graphData = await graphRes.json();
      setFullGraph(graphData);
      renderFullGraph(graphData);
      fetchPreQueryProcessing(uploaded.database_id);

      setMessage(`已載入 ${uploaded.filename}：${graphData.node_count} tables, ${graphData.edge_count} foreign keys。`);
      refreshSavedDatabases();
    } catch (err) {
      setMessage(`錯誤：${err.message}`);
    } finally {
      setLoading(false);
      event.target.value = '';
    }
  };

  const fetchClusterSummary = async (clusterId, focusTableForSummary) => {
    if (!databaseInfo || !focusTableForSummary) return null;

    setClusterSummaryLoading(true);

    try {
      const res = await fetch(
        `${API_BASE}/api/databases/${databaseInfo.database_id}/clusters/${clusterId}/summary?table=${encodeURIComponent(focusTableForSummary)}&depth=${focusDepth}`
      );

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Cluster summary failed');
      }

      return await res.json();
    } catch (err) {
      setMessage(`產生 summary 說明失敗：${err.message}`);
      return null;
    } finally {
      setClusterSummaryLoading(false);
    }
  };

  const expandSummaryNode = async (nodeId, nodeData) => {
    if (expandingSummaryNodeId) return;
    if (viewMode === 'query-summary') {
      if (!databaseInfo || !Array.isArray(nodeData.tables) || nodeData.tables.length === 0) {
        setClusterDetail(nodeData);
        markSelectedNode(nodeId);
        setMessage('這個 summary node 沒有可展開的 table list。');
        return;
      }

      pushCurrentGraphState();
      setClusterDetail(nodeData);
      markSelectedNode(nodeId);
      setExpandingSummaryNodeId(nodeId);
      setMessage(`正在展開 ${nodeData.label}...`);

      try {
        const visibleTableIds = elements
          .filter((el) => el.data && ['query', 'bridge', 'table', 'focus'].includes(el.data.node_type))
          .map((el) => el.data.id);

        const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/summary-node/expand`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cluster_id: nodeId,
            tables: nodeData.tables,
            visible_table_ids: visibleTableIds,
            direct_expand_threshold: 4
          })
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || 'Summary node expansion failed');
        }

        const expansion = await res.json();
        const positionsBeforeExpansion = captureGraphPositions();
        const expansionCenter = positionsBeforeExpansion.get(nodeId) || { x: 0, y: 0 };

        skipNextAutoLayoutRef.current = true;

        setElements((currentElements) => {
          const existingIds = new Set(currentElements.map((el) => el.data?.id));
          const kept = currentElements
            .filter((el) => {
              if (!el.data) return true;
              if (el.data.id === nodeId) return false;
              if (el.data.source === nodeId || el.data.target === nodeId) return false;
              return true;
            })
            .map((el) => {
              if (!el.data || el.data.source || el.data.target) return el;
              const position = positionsBeforeExpansion.get(el.data.id);
              return position ? { ...el, position } : el;
            });

          const candidateNewNodes = expansion.nodes.filter((node) => !existingIds.has(node.id));
          const occupiedPositions = kept
            .filter((el) => el.data && !el.data.source && !el.data.target && el.data.node_type !== 'new_marker')
            .map((el) => el.position)
            .filter(Boolean);
          const expansionPositions = getExpansionNodePositions(expansionCenter, candidateNewNodes.length, occupiedPositions);

          const newNodes = candidateNewNodes.map((node, index) => ({
            data: {
              ...node,
              id: node.id,
              label: node.label,
              displayLabel: node.node_type === 'summary'
                ? formatSummaryNodeLabel(node)
                : node.label,
              is_newly_expanded: true
            },
            classes: `${node.node_type === 'query' ? 'query-node ' : ''}newly-expanded`.trim(),
            position: expansionPositions[index]
          }));

          const keptIdsAfterSummaryRemoval = new Set(kept.map((el) => el.data?.id));
          const newEdges = expansion.edges
            .filter((edge) => {
              if (existingIds.has(edge.id)) return false;
              const sourceExists = keptIdsAfterSummaryRemoval.has(edge.source) || newNodes.some((n) => n.data.id === edge.source);
              const targetExists = keptIdsAfterSummaryRemoval.has(edge.target) || newNodes.some((n) => n.data.id === edge.target);
              return sourceExists && targetExists;
            })
            .map((edge) => ({
              data: {
                ...edge,
                id: edge.id,
                source: edge.source,
                target: edge.target,
                label: edge.edge_type === 'summary_edge' || edge.edge_type === 'metaedge'
                  ? edge.label
                  : `${edge.from_column} → ${edge.to_column}`,
                displayLabel: edge.edge_type === 'summary_edge'
                  ? `${edge.label}\nscore ${Number(edge.score ?? 0).toFixed(2)}`
                  : edge.edge_type === 'metaedge'
                    ? `metaedge\nwt ${Number(edge.weight ?? 0).toFixed(2)}`
                    : `${edge.from_column} → ${edge.to_column}`
              }
            }));

          const markerNodes = newNodes.map((nodeElement) => createNewExpansionMarker(nodeElement));

          return [...kept, ...newNodes, ...markerNodes, ...newEdges];
        });

        setMessage(`已展開 ${nodeData.label}：新增 ${expansion.nodes.length} node(s)。`);
        setTableDetail(null);
        setClusterDetail(null);
      } catch (err) {
        setMessage(`展開 query summary node 失敗：${err.message}`);
      } finally {
        setExpandingSummaryNodeId((current) => current === nodeId ? '' : current);
      }
      return;
    }

    const focusTableForExpansion = currentFocusTable || selectedTable;

    if (!databaseInfo || !focusTableForExpansion) {
      setMessage('請先選擇 focus table。');
      return;
    }

    pushCurrentGraphState();

    setExpandingSummaryNodeId(nodeId);
    setClusterDetail(nodeData);
    markSelectedNode(nodeId);

    fetchClusterSummary(nodeId, focusTableForExpansion).then((summary) => {
      if (summary) {
        setClusterDetail((current) => ({
          ...current,
          llm_summary: summary
        }));
        updateNodeLabel(nodeId, summary.module_name_zh, summary);
      }
    });

    try {
      const res = await fetch(
        `${API_BASE}/api/databases/${databaseInfo.database_id}/clusters/${nodeId}/expand?table=${encodeURIComponent(focusTableForExpansion)}&depth=${focusDepth}`
      );

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Cluster expansion failed');
      }

      const expansion = await res.json();
      const positionsBeforeExpansion = captureGraphPositions();
      const expansionCenter = positionsBeforeExpansion.get(nodeId) || { x: 0, y: 0 };

      skipNextAutoLayoutRef.current = true;

      setElements((currentElements) => {
        const existingIds = new Set(currentElements.map((el) => el.data?.id));
        const kept = currentElements
          .filter((el) => {
            if (!el.data) return true;
            if (el.data.id === nodeId) return false;
            if (el.data.source === nodeId || el.data.target === nodeId) return false;
            return true;
          })
          .map((el) => {
            if (!el.data || el.data.source || el.data.target) return el;
            const position = positionsBeforeExpansion.get(el.data.id);
            return position ? { ...el, position } : el;
          });

        const candidateNewNodes = expansion.nodes.filter((node) => !existingIds.has(node.id));
        const occupiedPositions = kept
          .filter((el) => el.data && !el.data.source && !el.data.target && el.data.node_type !== 'new_marker')
          .map((el) => el.position)
          .filter(Boolean);
        const expansionPositions = getExpansionNodePositions(expansionCenter, candidateNewNodes.length, occupiedPositions);

        const newNodes = candidateNewNodes.map((node, index) => ({
          data: {
            ...node,
            id: node.id,
            label: node.label,
            displayLabel: node.node_type === 'summary'
              ? formatSummaryNodeLabel(node)
              : node.label,
            is_newly_expanded: true
          },
          classes: `${node.node_type === 'query' ? 'query-node ' : ''}newly-expanded`.trim(),
          position: expansionPositions[index]
        }));

        const keptIdsAfterSummaryRemoval = new Set(kept.map((el) => el.data?.id));
        const newEdges = expansion.edges
          .filter((edge) => {
            if (existingIds.has(edge.id)) return false;
            const sourceExists = keptIdsAfterSummaryRemoval.has(edge.source) || newNodes.some((n) => n.data.id === edge.source);
            const targetExists = keptIdsAfterSummaryRemoval.has(edge.target) || newNodes.some((n) => n.data.id === edge.target);
            return sourceExists && targetExists;
          })
          .map((edge) => ({
            data: {
              ...edge,
              id: edge.id,
              source: edge.source,
              target: edge.target,
              label: edge.edge_type === 'summary_edge' || edge.edge_type === 'metaedge'
                ? edge.label
                : `${edge.from_column} → ${edge.to_column}`,
              displayLabel: edge.edge_type === 'summary_edge'
                ? `${edge.label}
score ${Number(edge.score ?? 0).toFixed(2)}`
                : edge.edge_type === 'metaedge'
                  ? `metaedge
wt ${Number(edge.weight ?? 0).toFixed(2)}`
                  : `${edge.from_column} → ${edge.to_column}`
            }
          }));

        const markerNodes = newNodes.map((nodeElement) => createNewExpansionMarker(nodeElement));

        return [...kept, ...newNodes, ...markerNodes, ...newEdges];
      });

      setMessage(`已展開 ${nodeData.label}：${expansion.nodes.length} table(s)。`);
      setTableDetail(null);
      setClusterDetail(null);
      setEdgeDetail(null);
    } catch (err) {
      setMessage(`展開 summary node 失敗：${err.message}`);
    } finally {
      setExpandingSummaryNodeId((current) => current === nodeId ? '' : current);
    }
  };

  const handleCyReady = useCallback((cy) => {
    cyRef.current = cy;

    // CytoscapeComponent may call cy callback again after re-rendering.
    // Remove old handlers first to avoid duplicated tap / hover events.
    cy.off('tap', 'node');
    cy.off('tap', 'edge');
    cy.off('tap.clear-selection');
    cy.off('drag', 'node');
    cy.off('mouseover', 'edge');
    cy.off('mouseout', 'edge');

    cy.on('tap', 'node', (event) => {
      let node = event.target;
      let data = node.data();

      // If the user clicks directly on the green marker, treat it as clicking
      // the marked node. The marker sits above the real node, so returning here
      // makes the node appear unselectable.
      if (data.node_type === 'new_marker') {
        const targetNode = cy.getElementById(data.target_node_id);
        if (!targetNode || targetNode.length === 0) return;
        node = targetNode;
        data = targetNode.data();
      }

      cy.edges().removeClass('inspected-edge edge-hover');
      cy.edges().unselect();

      // If the node has the new-expanded green marker, clicking it should still
      // behave like a normal selection. Clear the marker first, then persist the
      // selected-node class so the teal selection color survives the element update.
      clearNewExpandedMarker(data.id);
      markSelectedNode(data.id);

      if (data.node_type === 'summary') {
        setTableDetail(null);
        setEdgeDetail(null);
        setClusterDetail(data);
        setSelectedTable('');

        const focusTableForSummary = currentFocusTable || selectedTable;
        if (viewMode !== 'query-summary' && focusTableForSummary) {
          fetchClusterSummary(data.id, focusTableForSummary).then((summary) => {
            if (summary) {
              setClusterDetail((current) => current?.id === data.id
                ? { ...current, llm_summary: summary }
                : current
              );
              updateNodeLabel(data.id, summary.module_name_zh, summary);
            }
          });
        }
      } else {
        fetchTableDetail(data.id, data);
      }
    });

    cy.on('tap', 'edge', (event) => {
      const edge = event.target;
      const data = edge.data();

      markSelectedNode('');
      cy.edges().removeClass('inspected-edge edge-hover');
      cy.edges().unselect();
      edge.select();
      edge.addClass('inspected-edge edge-hover');

      setTableDetail(null);
      setClusterDetail(null);
      setSelectedTable('');
      setEdgeDetail(enrichEdgeDetail(data, fullGraph));
    });

    cy.on('tap.clear-selection', (event) => {
      if (event.target !== cy) return;
      markSelectedNode('');
      cy.edges().removeClass('inspected-edge edge-hover');
      cy.edges().unselect();
    });

    cy.on('drag', 'node', (event) => {
      const data = event.target.data();
      if (data.node_type === 'new_marker') return;
      if (data.is_newly_expanded || event.target.hasClass('newly-expanded')) {
        clearNewExpandedMarker(data.id);
      }
    });

    cy.on('mouseover', 'edge', (event) => {
      event.target.addClass('edge-hover');
      event.target.select();
    });

    cy.on('mouseout', 'edge', (event) => {
      if (event.target.hasClass('inspected-edge')) return;
      event.target.removeClass('edge-hover');
      event.target.unselect();
    });
  }, [
    markSelectedNode,
    clearNewExpandedMarker,
    fetchTableDetail,
    fetchClusterSummary,
    updateNodeLabel,
    currentFocusTable,
    selectedTable,
    viewMode,
    fullGraph
  ]);

  const focusRecommendedTable = (tableName) => {
    if (!tableName) return;
    setSelectedTable(tableName);
    markSelectedNode(tableName);
    fetchTableDetail(tableName);
    pushCurrentGraphState();
    renderFocusSummaryGraph(tableName, focusDepth);
  };

  const handleSavedDatabaseChange = (event) => {
    const databaseId = event.target.value;
    setSavedDatabaseId(databaseId);

    if (databaseId) {
      loadDatabaseById(databaseId);
    }
  };

  const handleSearchChange = (event) => {
    const tableName = event.target.value;
    setSelectedTable(tableName);

    if (tableName) {
      markSelectedNode(tableName);
      fetchTableDetail(tableName);
    }
  };

  const handleSummaryButton = () => {
    if (!selectedTable) {
      setMessage('請先選擇或點擊一張 table。');
      return;
    }

    pushCurrentGraphState();
    renderFocusSummaryGraph(selectedTable, focusDepth);
  };

  const handleFullGraphButton = () => {
    if (!fullGraph) return;

    pushCurrentGraphState();
    renderFullGraph(fullGraph);
    setCurrentFocusTable('');
    setMessage(`已切回完整 graph：${fullGraph.node_count} tables, ${fullGraph.edge_count} foreign keys。`);
  };

  const handleDepthChange = (event) => {
    const depth = Number(event.target.value);
    setFocusDepth(depth);

    if (viewMode === 'summary' && currentFocusTable) {
      pushCurrentGraphState();
      renderFocusSummaryGraph(currentFocusTable, depth);
    }
  };

  const closeInspector = useCallback(() => {
    setTableDetail(null);
    setClusterDetail(null);
    setEdgeDetail(null);
    setInspectorLoadingTable('');
    markSelectedNode('');
    const cy = cyRef.current;
    if (cy) {
      cy.edges().removeClass('edge-hover inspected-edge');
      cy.edges().unselect();
    }
  }, [markSelectedNode]);

  const currentViewLabel = viewMode === 'query-summary'
    ? 'Query-aware Summary Graph'
    : viewMode === 'summary'
      ? 'Focus Summary View'
      : viewMode === 'focus'
        ? 'Focus Graph'
        : 'Full Schema Graph';

  const visibleNodeCount = elements.filter((el) => el?.data?.source === undefined).length;
  const visibleEdgeCount = elements.filter((el) => el?.data?.source !== undefined).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>QueryNav</h1>
        <p className="subtitle">Schema Graph Viewer</p>

        <label className="upload-box">
          <input type="file" accept=".db,.sqlite,.sqlite3" onChange={handleUpload} disabled={loading} />
          {loading ? '處理中...' : '上傳 SQLite .db'}
        </label>

        <label className="field-label">已儲存在伺服器的 database</label>
        <select
          className="select"
          value={savedDatabaseId}
          onChange={handleSavedDatabaseChange}
          disabled={loading || savedDatabases.length === 0}
        >
          <option value="">{savedDatabases.length === 0 ? '尚無已儲存 database' : '選擇 database'}</option>
          {savedDatabases.map((database) => (
            <option key={database.database_id} value={database.database_id}>
              {database.filename} ({database.table_count} tables, {database.foreign_key_count} FKs)
            </option>
          ))}
        </select>

        <div className="status">{message}</div>

        {databaseInfo && (
          <div className="info-card">
            <div><strong>Database ID</strong></div>
            <code>{databaseInfo.database_id}</code>
            <div className="stats">
              <span>{databaseInfo.table_count} tables</span>
              <span>{databaseInfo.foreign_key_count} FKs</span>
            </div>
          </div>
        )}

        {databaseInfo && (
          <div className="current-view-card">
            <div className="card-heading-row">
              <strong>Current View</strong>
              <span className="mode-pill">{currentViewLabel}</span>
            </div>
            <div className="view-stat-grid">
              <span>Visible nodes</span>
              <strong>{visibleNodeCount}</strong>
              <span>Visible edges</span>
              <strong>{visibleEdgeCount}</strong>
              <span>Query set</span>
              <strong>{querySet.length}</strong>
              <span>Budget</span>
              <strong>{nodeBudget}</strong>
            </div>
          </div>
        )}

        {tableNames.length > 0 && (
          <div className="legend-card">
            <div className="card-heading-row">
              <strong>Legend</strong>
              <span className="subtle-pill">Graph semantics</span>
            </div>
            <div className="legend-grid">
              <span><i className="legend-node table" /> Table</span>
              <span><i className="legend-node query" /> Query table</span>
              <span><i className="legend-node bridge" /> Bridge table</span>
              <span><i className="legend-node summary" /> Summary node</span>
              <span><i className="legend-edge fk" /> Original FK</span>
              <span><i className="legend-edge meta" /> Metaedge / compressed path</span>
              <span><i className="legend-edge summary" /> Summary edge</span>
            </div>
            <div className="section-note">Edge labels are hidden by default. Hover an edge to inspect its relation and weight.</div>
          </div>
        )}

        {tableNames.length > 0 && (
          <div className="query-set-card">
            <div className="query-set-header">
              <strong>Query Set</strong>
              <span>{querySet.length} table(s)</span>
            </div>
            <p className="muted">
              將關心的 tables 加入 Query Set，再用 node budget 產生 query-aware summary graph。
            </p>

            <div className="query-chip-list editable-query-list">
              {querySet.length === 0 ? (
                <span className="empty-query-hint">尚未加入任何 table</span>
              ) : (
                querySet.map((tableName) => (
                  <button
                    key={tableName}
                    className="query-chip active-query-chip"
                    onClick={() => {
                      setSelectedTable(tableName);
                      markSelectedNode(tableName);
                      fetchTableDetail(tableName);
                    }}
                    title="點擊查看 table；按 × 可移除"
                  >
                    <span>{tableName}</span>
                    <span
                      className="chip-remove"
                      onClick={(event) => {
                        event.stopPropagation();
                        removeFromQuerySet(tableName);
                      }}
                    >
                      ×
                    </span>
                  </button>
                ))
              )}
            </div>

            <div className="button-row query-button-row">
              <button
                className="secondary-button"
                onClick={useRecommendedQuerySet}
                disabled={!preQueryInfo?.recommended_query_set?.length}
              >
                Use Recommended
              </button>
              <button
                className="secondary-button"
                onClick={clearQuerySet}
                disabled={querySet.length === 0}
              >
                Clear
              </button>
            </div>

            <div className="budget-control-header">
              <label className="field-label compact-field-label">Node budget</label>
              <span className="budget-value">{nodeBudget} visible table nodes</span>
            </div>
            <div className="budget-control">
              <input
                className="budget-slider"
                type="range"
                min="2"
                max="80"
                step="1"
                value={nodeBudget}
                onChange={(event) => setNodeBudget(Number(event.target.value))}
                disabled={loading}
              />
              <input
                className="budget-number-input"
                type="number"
                min="2"
                max="200"
                value={nodeBudget}
                onChange={(event) => {
                  const nextValue = Number(event.target.value);
                  if (Number.isNaN(nextValue)) return;
                  setNodeBudget(Math.max(2, Math.min(200, nextValue)));
                }}
                disabled={loading}
              />
            </div>
            <div className="budget-hint">
              可輸入 2–200；預設 slider 到 80，方便測試更大的 summary graph budget。
            </div>

            <button
              className="primary-action-button"
              onClick={generateQuerySummaryGraph}
              disabled={loading || querySet.length === 0}
            >
              Generate Summary Graph
            </button>
          </div>
        )}

        {preQueryProgress.active && (
          <div className="cluster-overview-card preprocessing-progress-card">
            <div className="card-heading-row">
              <strong>Pre-query Processing</strong>
              <span className="status-pill working">Running</span>
            </div>
            <div className="prequery-cache-status">
              <span className="loading-dot" />
              <span>{preQueryProgress.stage}</span>
              {preQueryProgress.elapsedSeconds > 0 && (
                <span className="progress-elapsed">{preQueryProgress.elapsedSeconds}s</span>
              )}
            </div>
            <div className="progress-note">
              Pre-query results are now stored in the backend cache. If the same database and parameters were processed before,
              this step should return quickly from cache; otherwise the backend will compute it once and save the result.
            </div>
          </div>
        )}

        {preQueryInfo && (
          <div className="cluster-overview-card collapsible-card">
            <div className="card-heading-row">
              <strong>Pre-query Processing</strong>
              {preQueryInfo.cache_hit ? (
                <span className="status-pill cached">Loaded from cache</span>
              ) : (
                <span className="status-pill computed">Computed + cached</span>
              )}
              <button
                className="text-button"
                onClick={() => setShowPreQueryDetails((value) => !value)}
              >
                {showPreQueryDetails ? 'Hide details' : 'Show details'}
              </button>
            </div>
            <div className="muted">
              Preprocessing is ready. Recommended query tables and schema clusters were generated from paper-based edge weights and importance scores.
            </div>

            <div className="process-checklist">
              <span>✓ Edge weights computed</span>
              <span>✓ Importance scores computed</span>
              <span>✓ Initial clusters generated</span>
              <span>✓ Recommended query set ready</span>
            </div>

            <div className="prequery-stats">
              <span>{preQueryInfo.table_count} tables</span>
              <span>{preQueryInfo.edge_count} weighted edges</span>
              <span>{preQueryInfo.clusters?.length || 0} clusters</span>
              <span>Q {Number(preQueryInfo.modularity_score ?? 0).toFixed(3)}</span>
            </div>

            <h3>Recommended Initial Query Set</h3>
            <div className="query-chip-list">
              {(preQueryInfo.recommended_query_set || []).map((tableName) => (
                <button
                  key={tableName}
                  className="query-chip"
                  onClick={() => addToQuerySet(tableName)}
                  title="Add representative table to Query Set"
                >
                  {tableName}
                </button>
              ))}
            </div>

            {showPreQueryDetails && (
              <>
                <h3>Clustering Method</h3>
                <div className="score-grid compact-score-grid">
                  <span>Method</span>
                  <strong>{preQueryInfo.clustering_method || 'paper_greedy_weighted_modularity'}</strong>
                  <span>Merge count</span>
                  <strong>{Number(preQueryInfo.merge_count ?? 0).toFixed(0)}</strong>
                  <span>Total edge strength</span>
                  <strong>{Number(preQueryInfo.total_edge_strength ?? 0).toFixed(3)}</strong>
                </div>

                <h3>Edge Weight Summary</h3>
                <div className="score-grid compact-score-grid">
                  <span>Avg edge score</span>
                  <strong>{Number(preQueryInfo.edge_weight_summary?.average_score ?? 0).toFixed(2)}</strong>
                  <span>Max edge score</span>
                  <strong>{Number(preQueryInfo.edge_weight_summary?.max_score ?? 0).toFixed(2)}</strong>
                  <span>Avg weight</span>
                  <strong>{Number(preQueryInfo.edge_weight_summary?.average_weight ?? 0).toFixed(2)}</strong>
                </div>

                <h3>Top Importance Tables</h3>
                <div className="importance-list">
                  {(preQueryInfo.top_importance_tables || []).slice(0, 5).map((item) => (
                    <button
                      key={item.table}
                      className="importance-item"
                      onClick={() => focusRecommendedTable(item.table)}
                      title={item.reason}
                    >
                      <span>#{item.rank} {item.table}</span>
                      <strong>{Number(item.importance_score ?? 0).toFixed(2)}</strong>
                    </button>
                  ))}
                </div>

                <h3>Initial Clusters</h3>
                <div className="section-note">Sorted by representative importance. Qᵢ is the modularity contribution.</div>
                <div className="initial-cluster-list">
                  {(preQueryInfo.clusters || []).slice(0, 6).map((cluster) => (
                    <div key={cluster.cluster_id} className="initial-cluster-item">
                      <div className="cluster-title-line">
                        <span>{cluster.label}</span>
                        {cluster.query_set_candidate && <small className="candidate-badge">recommended</small>}
                      </div>
                      <div className="cluster-representative-line">
                        <span>Representative</span>
                        <button onClick={() => focusRecommendedTable(cluster.representative_table)}>{cluster.representative_table}</button>
                      </div>
                      <div className="cluster-metric-grid">
                        <span>Rep. importance</span>
                        <strong>{Number(cluster.representative_score ?? 0).toFixed(2)}</strong>
                        <span>Qᵢ</span>
                        <strong>{Number(cluster.modularity_contribution ?? 0).toFixed(3)}</strong>
                        <span>eᵢᵢ</span>
                        <strong>{Number(cluster.e_ii ?? 0).toFixed(3)}</strong>
                        <span>aᵢ</span>
                        <strong>{Number(cluster.a_i ?? 0).toFixed(3)}</strong>
                      </div>
                      <div className="cluster-table-preview">
                        {cluster.table_count} tables · {cluster.tables.slice(0, 5).join(', ')}{cluster.tables.length > 5 ? ', ...' : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}





        {tableNames.length > 0 && (
          <>
            <label className="field-label">搜尋 / 選擇 table</label>
            <select className="select" value={selectedTable} onChange={handleSearchChange}>
              <option value="">選擇 table</option>
              {tableNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>

            <div className="button-row selected-table-actions">
              <button
                className={selectedTable && querySet.includes(selectedTable) ? 'secondary-button danger-button' : 'secondary-button'}
                onClick={toggleSelectedTableQuerySet}
                disabled={!selectedTable}
              >
                {selectedTable && querySet.includes(selectedTable) ? 'Remove selected from Query Set' : 'Add selected to Query Set'}
              </button>
            </div>

            <div className="button-row selected-table-actions">
              <button className="secondary-button" onClick={handleSummaryButton} disabled={!selectedTable}>
                Open Focus Summary
              </button>
            </div>
          </>
        )}

        {querySummaryInfo && (
          <div className="focus-card query-summary-card">
            <strong>Query-aware Summary Graph</strong>
            <div>Query tables: {querySummaryInfo.query_tables.join(', ')}</div>
            <div>Node budget: {querySummaryInfo.node_budget}</div>
            <div>Query nodes: {querySummaryInfo.query_node_count ?? querySummaryInfo.query_tables.length}</div>
            <div>Bridge nodes: {querySummaryInfo.bridge_node_count ?? 0}</div>
            <div>Summary nodes: {querySummaryInfo.summary_node_count}</div>
            <div>Compressed hidden tables: {querySummaryInfo.hidden_node_count}</div>
            <div>Compressed edges: {querySummaryInfo.stats?.compressed_edge_count ?? 0}</div>
            <div>Budget respected: {querySummaryInfo.stats?.budget_respected === false ? 'No, connectivity preserved first' : 'Yes'}</div>
            <div>Node reduction: {(Number(querySummaryInfo.stats?.node_reduction_ratio ?? 0) * 100).toFixed(1)}%</div>
            <div>Edge reduction: {(Number(querySummaryInfo.stats?.edge_reduction_ratio ?? 0) * 100).toFixed(1)}%</div>


            {(querySummaryInfo.paths || []).length > 0 && (
              <>
                <h3>Preserved Join Paths</h3>
                <div className="path-list">
                  {querySummaryInfo.paths.map((path) => (
                    <div key={`${path.source}-${path.target}`} className="path-item">
                      <strong>{path.source} → {path.target}</strong>
                      <span>{path.path.join(' → ')}</span>
                      <small>weight {Number(path.total_weight ?? 0).toFixed(2)} · avg edge score {Number(path.average_edge_score ?? 0).toFixed(2)}</small>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {focusInfo && (
          <div className="focus-card">
            <strong>Summary View</strong>
            <div>Focus: {focusInfo.focus_table}</div>
            <div>Visible table nodes: {focusInfo.visible_node_count}</div>
            <div>Summary nodes: {focusInfo.summary_node_count}</div>
            <div>Compressed hidden tables: {focusInfo.hidden_node_count}</div>
          </div>
        )}

        {clusterDetail && (
          <div className="cluster-card">
            <h2>{clusterDetail.llm_summary?.module_name_zh || clusterDetail.label}</h2>
            <div>{clusterDetail.table_count} table(s)</div>

            {clusterSummaryLoading ? (
              <p className="muted">Generating English summary...</p>
            ) : (
              <>
                <p>{clusterDetail.llm_summary?.description_zh || clusterDetail.description}</p>

                {clusterDetail.llm_summary && (
                  <>
                    <h3>Key Tables</h3>
                    <div className="hidden-list">{clusterDetail.llm_summary.key_tables?.join(', ')}</div>

                    <h3>Reason</h3>
                    <p>{clusterDetail.llm_summary.reason_zh}</p>

                    <div className="summary-source">
                      Source: {clusterDetail.llm_summary.source === 'llm' ? 'LLM' : 'Fallback'}
                    </div>
                  </>
                )}
              </>
            )}

            <h3>Tables</h3>
            <div className="hidden-list">{clusterDetail.tables?.join(', ')}</div>
          </div>
        )}

        {tableDetail && (
          <div className="detail-card">
            <h2>{tableDetail.table.name}</h2>
            <button
              className={querySet.includes(tableDetail.table.name) ? 'query-toggle-button remove-query-button' : 'query-toggle-button'}
              onClick={() => querySet.includes(tableDetail.table.name)
                ? removeFromQuerySet(tableDetail.table.name)
                : addToQuerySet(tableDetail.table.name)}
            >
              {querySet.includes(tableDetail.table.name) ? 'Remove from Query Set' : 'Add to Query Set'}
            </button>
            <div className="detail-row">Rows: {tableDetail.table.row_count ?? '?'}</div>
            <div className="detail-row">PK: {tableDetail.table.primary_keys.join(', ') || 'None'}</div>

            {tableDetail.node && (
              <div className="score-panel">
                <div className="score-title">Importance Score</div>
                <div className="score-value">{Number(tableDetail.node.importance_score ?? 0).toFixed(2)}</div>
                <div className="score-grid">
                  <span>IC(R)</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_initial_importance_ic ?? 0).toFixed(2)}</strong>
                  <span>log |R|</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_log_tuple_count ?? 0).toFixed(2)}</strong>
                  <span>Σ entropy</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_attribute_entropy_sum ?? 0).toFixed(2)}</strong>
                  <span>Self transfer</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_self_transfer_probability ?? 0).toFixed(2)}</strong>
                  <span>Outgoing transfer</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_outgoing_transfer_probability ?? 0).toFixed(2)}</strong>
                  <span>Stationary raw</span>
                  <strong>{Number(tableDetail.node.score_breakdown?.paper_stationary_importance_raw ?? 0).toFixed(2)}</strong>
                </div>
                <div className="score-note">
                  Final score = normalized stationary value of Vᵢ₊₁ = VᵢΠ, initialized by IC(R)=log|R|+ΣH(R.A).
                </div>
              </div>
            )}

            <h3>Columns</h3>
            <div className="column-list">
              {tableDetail.table.columns.map((col) => (
                <div key={col.name} className="column-item">
                  <span>{col.name}</span>
                  <small>{col.type || 'UNKNOWN'}{col.is_primary_key ? ' · PK' : ''}</small>
                </div>
              ))}
            </div>

            <h3>Foreign keys</h3>
            {(tableDetail.outgoing_edges || []).length === 0 ? (
              <p className="muted">No outgoing foreign keys.</p>
            ) : (
              tableDetail.outgoing_edges.map((edge) => (
                <div key={edge.id} className="fk-item">
                  <div>{edge.source}.{edge.from_column} → {edge.target}.{edge.to_column}</div>
                  <EdgeMetrics edge={edge} />
                </div>
              ))
            )}

            <h3>Referenced by</h3>
            {tableDetail.referenced_by.length === 0 ? (
              <p className="muted">No incoming references.</p>
            ) : (
              tableDetail.referenced_by.map((edge) => (
                <div key={edge.id} className="fk-item">
                  <div>{edge.source}.{edge.from_column} → {edge.target}.{edge.to_column}</div>
                  <EdgeMetrics edge={edge} />
                </div>
              ))
            )}
          </div>
        )}
      </aside>

      <main className="graph-area">
        <div className="graph-layout-toolbar">
          <button
            className="graph-toolbar-button layout-button"
            onClick={rerunLayout}
            disabled={elements.length === 0}
            title="重新排列目前 graph"
          >
            重新排列
          </button>
        </div>

        <div className="graph-toolbar">
          <button
            className="graph-toolbar-button"
            onClick={restorePreviousStep}
            disabled={graphHistory.length === 0}
            title={graphHistory.length === 0 ? '目前沒有上一步' : '回到上一個 graph 狀態'}
          >
            ← 回到上一步
          </button>
          <button
            className="graph-toolbar-button primary"
            onClick={handleFullGraphButton}
            disabled={!fullGraph}
            title="回到完整 schema graph"
          >
            Full Graph
          </button>
        </div>

        {(tableDetail || clusterDetail || edgeDetail) && (
          <aside className={clusterDetail ? 'node-inspector summary-inspector' : edgeDetail ? 'node-inspector edge-inspector' : 'node-inspector'}>
            <div className="inspector-header">
              <div>
                <div className="inspector-eyebrow">{clusterDetail ? 'Summary node' : edgeDetail ? 'Edge' : 'Table node'}</div>
                <h2>{clusterDetail?.llm_summary?.module_name_zh || clusterDetail?.label || tableDetail?.table?.name || edgeDetail?.label || edgeDetail?.id}</h2>
              </div>
              <button className="inspector-close" onClick={closeInspector} title="Close inspector">×</button>
            </div>

            {tableDetail && (
              <div className="inspector-body">
                <div className="inspector-actions">
                  <button
                    className={querySet.includes(tableDetail.table.name) ? 'inspector-action danger' : 'inspector-action primary'}
                    onClick={() => querySet.includes(tableDetail.table.name)
                      ? removeFromQuerySet(tableDetail.table.name)
                      : addToQuerySet(tableDetail.table.name)}
                  >
                    {querySet.includes(tableDetail.table.name) ? 'Remove from Query Set' : 'Add to Query Set'}
                  </button>
                </div>

                {(tableDetail.loading || inspectorLoadingTable === tableDetail.table.name) && (
                  <div className="inspector-loading">Loading table details...</div>
                )}

                <div className="inspector-stat-row">
                  <span>Rows</span>
                  <strong>{tableDetail.table.row_count ?? '?'}</strong>
                </div>
                <div className="inspector-stat-row">
                  <span>Primary key</span>
                  <strong>{tableDetail.table.primary_keys.join(', ') || 'None'}</strong>
                </div>
                {tableDetail.node && (
                  <div className="inspector-stat-row">
                    <span>Importance</span>
                    <strong>{Number(tableDetail.node.importance_score ?? 0).toFixed(2)}</strong>
                  </div>
                )}

                <h3>Columns</h3>
                <div className="inspector-column-list">
                  {tableDetail.table.columns.length === 0 ? (
                    <div className="inspector-empty">Column metadata is loading...</div>
                  ) : tableDetail.table.columns.map((col) => (
                    <div key={col.name} className="inspector-column-item">
                      <span>{col.name}</span>
                      <small>{col.type || 'UNKNOWN'}{col.is_primary_key ? ' · PK' : ''}</small>
                    </div>
                  ))}
                </div>

                <h3>Relationships</h3>
                <div className="inspector-relation-summary">
                  <span>Outgoing FKs</span>
                  <strong>{tableDetail.outgoing_edges?.length || 0}</strong>
                  <span>Referenced by</span>
                  <strong>{tableDetail.referenced_by?.length || 0}</strong>
                </div>

                {(tableDetail.outgoing_edges || []).slice(0, 4).map((edge) => (
                  <div key={edge.id} className="inspector-edge-item">
                    {edge.source}.{edge.from_column} → {edge.target}.{edge.to_column}
                  </div>
                ))}
                {(tableDetail.referenced_by || []).slice(0, 4).map((edge) => (
                  <div key={edge.id} className="inspector-edge-item incoming">
                    {edge.source}.{edge.from_column} → {edge.target}.{edge.to_column}
                  </div>
                ))}
              </div>
            )}

            {edgeDetail && (
              <div className="inspector-body">
                <div className="inspector-stat-row">
                  <span>Type</span>
                  <strong>{edgeDetail.edge_type === 'metaedge' ? 'Metaedge / compressed path' : edgeDetail.edge_type === 'summary_edge' ? 'Summary edge' : 'Original FK'}</strong>
                </div>
                <div className="inspector-stat-row">
                  <span>Source</span>
                  <strong>{edgeDetail.source}</strong>
                </div>
                <div className="inspector-stat-row">
                  <span>Target</span>
                  <strong>{edgeDetail.target}</strong>
                </div>
                {edgeDetail.column_mapping && (
                  <div className="inspector-stat-row">
                    <span>Column mapping</span>
                    <strong>{edgeDetail.column_mapping}</strong>
                  </div>
                )}
                <div className="inspector-stat-row">
                  <span>Weight</span>
                  <strong>{Number(edgeDetail.weight ?? 0).toFixed(3)}</strong>
                </div>
                <div className="inspector-stat-row">
                  <span>Score</span>
                  <strong>{Number(edgeDetail.score ?? 0).toFixed(3)}</strong>
                </div>

                {edgeDetail.edge_type === 'metaedge' && (
                  <p className="inspector-description edge-description">
                    This metaedge represents a compressed join path between two visible nodes. It may summarize one or more hidden intermediate tables from the original schema graph.
                  </p>
                )}
                {edgeDetail.edge_type === 'summary_edge' && (
                  <p className="inspector-description edge-description">
                    This summary edge connects a visible node to a summary node. It indicates that at least one table inside the summary node is related to the visible graph.
                  </p>
                )}
                {(!edgeDetail.edge_type || edgeDetail.edge_type === 'fk') && (
                  <p className="inspector-description edge-description">
                    This is an original foreign-key relationship extracted from the SQLite schema.
                  </p>
                )}

                {edgeDetail.normalized_path?.length > 0 && (
                  <>
                    <h3>Complete metaedge path</h3>
                    <div className="inspector-edge-path">
                      {edgeDetail.normalized_path.join(' → ')}
                    </div>
                  </>
                )}

                {edgeDetail.path_column_mappings?.length > 0 && (
                  <>
                    <h3>Path column mappings</h3>
                    <div className="inspector-path-mapping-list">
                      {edgeDetail.path_column_mappings.map((item, index) => (
                        <div key={`${item.source}-${item.target}-${index}`} className="inspector-edge-item">
                          {item.label}
                        </div>
                      ))}
                    </div>
                  </>
                )}

                <h3>Edge metrics</h3>
                <EdgeMetrics edge={edgeDetail} />
              </div>
            )}

            {clusterDetail && (
              <div className="inspector-body">
                <div className="inspector-actions">
                  <button
                    className="inspector-action primary"
                    onClick={() => expandSummaryNode(clusterDetail.id, clusterDetail)}
                    disabled={expandingSummaryNodeId === clusterDetail.id || !Array.isArray(clusterDetail.tables) || clusterDetail.tables.length === 0}
                  >
                    {expandingSummaryNodeId === clusterDetail.id ? 'Expanding...' : 'Expand Summary Node'}
                  </button>
                </div>

                <div className="inspector-stat-row">
                  <span>Tables inside</span>
                  <strong>{clusterDetail.table_count || clusterDetail.tables?.length || 0}</strong>
                </div>
                {(clusterDetail.score_breakdown?.anchor_table || clusterDetail.representative_table) && (
                  <div className="inspector-stat-row">
                    <span>Representative</span>
                    <strong>{clusterDetail.score_breakdown?.anchor_table || clusterDetail.representative_table}</strong>
                  </div>
                )}
                {typeof clusterDetail.importance_score === 'number' && (
                  <div className="inspector-stat-row">
                    <span>Importance</span>
                    <strong>{Number(clusterDetail.importance_score).toFixed(2)}</strong>
                  </div>
                )}

                <p className="inspector-description">
                  {clusterDetail.llm_summary?.description_zh || clusterDetail.description || 'This summary node compresses related tables. Expand it to inspect the next level of schema detail.'}
                </p>

                <h3>Contained tables</h3>
                <div className="summary-table-list">
                  {(clusterDetail.tables || []).map((tableName) => (
                    <button
                      key={tableName}
                      className="summary-table-chip"
                      onClick={() => {
                        setSelectedTable(tableName);
                        fetchTableDetail(tableName);
                      }}
                    >
                      {tableName}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </aside>
        )}

        {elements.length === 0 ? (
          <div className="empty-state">
            <h2>尚未載入 graph</h2>
            <p>請先從左側上傳 SQLite database。</p>
          </div>
        ) : (
          <CytoscapeComponent
            elements={elements}
            stylesheet={cyStylesheet}
            cy={handleCyReady}
            style={{ width: '100%', height: '100%' }}
            wheelSensitivity={0.2}
            boxSelectionEnabled={false}
            layout={layoutOptions}
          />
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);