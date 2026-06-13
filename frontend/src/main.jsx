import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import './styles.css';

cytoscape.use(dagre);

const API_BASE = 'http://10.217.44.184:5417';

const cyStylesheet = [
  {
    selector: 'node',
    style: {
      shape: 'ellipse',
      width: 270,
      height: 145,
      'background-color': '#ffffff',
      'border-width': 2,
      'border-color': '#64748b',
      label: 'data(displayLabel)',
      color: '#0f172a',
      'font-size': 18,
      'font-weight': 800,
      'text-wrap': 'wrap',
      'text-max-width': 190,
      'text-valign': 'center',
      'text-halign': 'center',
      'line-height': 1.3,
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
    selector: 'node[node_type = "summary"]',
    style: {
      width: 310,
      height: 150,
      'background-color': '#fff7ed',
      'border-width': 3,
      'border-style': 'dashed',
      'border-color': '#f97316',
      color: '#7c2d12'
    }
  },
  {
    selector: 'node.selected-node',
    style: {
      'border-width': 4,
      'border-color': '#f59e0b',
      'background-color': '#fffbeb',
      'shadow-blur': 18,
      'shadow-color': '#f59e0b',
      'shadow-opacity': 0.35,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0
    }
  },
  {
    selector: 'edge',
    style: {
      width: 1.4,
      'line-color': '#94a3b8',
      'target-arrow-color': '#94a3b8',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      label: 'data(displayLabel)',
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
      width: 2.8,
      'line-style': 'dashed',
      'line-color': '#ea580c',
      'target-arrow-color': '#ea580c',
      'arrow-scale': 1.65,
      color: '#7c2d12',
      'font-weight': 800
    }
  },
  {
    selector: 'edge:selected',
    style: {
      width: 3.4,
      'line-color': '#2563eb',
      'target-arrow-color': '#2563eb',
      'arrow-scale': 1.8
    }
  }
];

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
      ? `${node.label}\n${node.table_count ?? 0} tables collapsed`
      : node.label;

    return {
      data: {
        ...node,
        id: node.id,
        label: node.label,
        displayLabel
      },
      classes: node.node_type === 'focus' ? 'focus-node' : ''
    };
  });

  const edges = edgesInput.map((edge) => ({
    data: {
      ...edge,
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.edge_type === 'summary_edge'
        ? edge.label
        : `${edge.from_column} → ${edge.to_column}`
    }
  }));

  return [...nodes, ...edges];
}

function App() {
  const cyRef = useRef(null);

  const [databaseInfo, setDatabaseInfo] = useState(null);
  const [fullGraph, setFullGraph] = useState(null);
  const [focusInfo, setFocusInfo] = useState(null);
  const [viewMode, setViewMode] = useState('full');
  const [focusDepth, setFocusDepth] = useState(1);
  const [elements, setElements] = useState([]);
  const [graphHistory, setGraphHistory] = useState([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [currentFocusTable, setCurrentFocusTable] = useState('');
  const [tableDetail, setTableDetail] = useState(null);
  const [clusterDetail, setClusterDetail] = useState(null);
  const [clusterSummaryLoading, setClusterSummaryLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('請先上傳 SQLite .db 檔案。');

  const tableNames = useMemo(() => {
    if (!fullGraph) return [];
    return fullGraph.nodes.map((n) => n.id).sort();
  }, [fullGraph]);


  const logFrontendEvent = useCallback(async (eventType, message, payload = {}) => {
    const logPayload = {
      ...payload,
      viewMode,
      selectedTable,
      currentFocusTable,
      focusDepth
    };

    console.log(`[SchemaLens Debug][${eventType}] ${message}`, logPayload);

    try {
      await fetch(`${API_BASE}/api/debug/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: eventType,
          message,
          payload: logPayload
        })
      });
    } catch (err) {
      console.warn('[SchemaLens Debug] Failed to send debug log to backend:', err);
    }
  }, [viewMode, selectedTable, currentFocusTable, focusDepth]);


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
    setGraphHistory((history) => history.slice(0, -1));
    logFrontendEvent('back_step_click', 'User restored previous graph state', { history_remaining: graphHistory.length - 1 });
    setMessage('已回到上一步。');
  }, [graphHistory, logFrontendEvent]);

  const rerunLayout = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) {
      setMessage('Graph is not ready yet.');
      return;
    }

    cy.nodes().unlock();

    const layout = cy.elements().layout({
      ...layoutOptions,
      animate: true,
      animationDuration: 450,
      fit: true,
      padding: 70
    });

    layout.run();

    layout.promiseOn('layoutstop').then(() => {
      cy.fit(cy.elements(), 70);
      setMessage('Graph layout has been rearranged.');
    });
  }, []);

  useEffect(() => {
    if (elements.length > 0) {
      setTimeout(rerunLayout, 30);
    }
  }, [elements, rerunLayout]);

  const markSelectedNode = useCallback((nodeId) => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.nodes().removeClass('selected-node');
    const node = cy.getElementById(nodeId);
    if (node && node.length > 0) {
      node.addClass('selected-node');
    }
  }, []);

  const renderFullGraph = useCallback((graphData) => {
    setElements(graphToElements(graphData.nodes, graphData.edges));
    setFocusInfo(null);
    setClusterDetail(null);
    setViewMode('full');
  }, []);

  const fetchTableDetail = useCallback(async (tableName) => {
    if (!databaseInfo || !tableName) return;
    setSelectedTable(tableName);
    setTableDetail(null);
    setClusterDetail(null);

    try {
      const res = await fetch(`${API_BASE}/api/databases/${databaseInfo.database_id}/tables/${tableName}`);
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to fetch table detail');
      }
      setTableDetail(await res.json());
    } catch (err) {
      setMessage(`取得 table detail 失敗：${err.message}`);
    }
  }, [databaseInfo, logFrontendEvent]);

  const updateNodeLabel = useCallback((nodeId, label, summary) => {
    setElements((currentElements) =>
      currentElements.map((el) => {
        if (!el.data || el.data.id !== nodeId) return el;
        const displayLabel = el.data.node_type === 'summary'
          ? `${label}\n${el.data.table_count ?? 0} tables collapsed`
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

    logFrontendEvent('summary_view_click', `User requested summary view for ${tableName}`, { tableName, depth });

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
      setCurrentFocusTable(tableName);
      setViewMode('summary');
      setClusterDetail(null);
      setElements(graphToElements(focusData.nodes, focusData.edges));

      refreshSummaryNodeLabels(focusData, tableName);

      logFrontendEvent('summary_view_success', `Summary view rendered for ${tableName}`, { visible_node_count: focusData.visible_node_count, summary_node_count: focusData.summary_node_count, hidden_node_count: focusData.hidden_node_count });
      setMessage(
        `Summary view：顯示 ${focusData.visible_node_count} table nodes + ${focusData.summary_node_count} summary nodes，壓縮 ${focusData.hidden_node_count} hidden tables。`
      );
    } catch (err) {
      logFrontendEvent('summary_view_error', err.message, { tableName, depth });
      setMessage(`Summary view 錯誤：${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [databaseInfo, focusDepth, refreshSummaryNodeLabels, logFrontendEvent]);

  const handleUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    logFrontendEvent('upload_click', `User selected file: ${file.name}`, { filename: file.name, size: file.size });

    setLoading(true);
    setMessage('上傳與解析中...');
    setDatabaseInfo(null);
    setFullGraph(null);
    setFocusInfo(null);
    setElements([]);
    setGraphHistory([]);
    setSelectedTable('');
    setCurrentFocusTable('');
    setTableDetail(null);
    setClusterDetail(null);

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

      const graphRes = await fetch(`${API_BASE}/api/databases/${uploaded.database_id}/graph`);
      if (!graphRes.ok) {
        const error = await graphRes.json();
        throw new Error(error.detail || 'Graph fetch failed');
      }

      const graphData = await graphRes.json();
      setFullGraph(graphData);
      renderFullGraph(graphData);

      logFrontendEvent('upload_success', `Loaded database: ${uploaded.filename}`, { database_id: uploaded.database_id, node_count: graphData.node_count, edge_count: graphData.edge_count });
      setMessage(`已載入 ${uploaded.filename}：${graphData.node_count} tables, ${graphData.edge_count} foreign keys。`);
    } catch (err) {
      logFrontendEvent('upload_error', err.message, { filename: file.name });
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
      logFrontendEvent('cluster_summary_error', err.message, { clusterId });
      setMessage(`產生 summary 說明失敗：${err.message}`);
      return null;
    } finally {
      setClusterSummaryLoading(false);
    }
  };

  const expandSummaryNode = async (nodeId, nodeData) => {
    const focusTableForExpansion = currentFocusTable || selectedTable;

    if (!databaseInfo || !focusTableForExpansion) {
      setMessage('請先選擇 focus table。');
      return;
    }

    pushCurrentGraphState();

    logFrontendEvent('summary_node_click', `User clicked summary node: ${nodeId}`, { nodeId, label: nodeData.label, table_count: nodeData.table_count });

    setClusterDetail(nodeData);
    markSelectedNode(nodeId);

    fetchClusterSummary(nodeId, focusTableForExpansion).then((summary) => {
      if (summary) {
        logFrontendEvent('cluster_summary_success', `Cluster summary generated for ${nodeId}`, summary);
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

      setElements((currentElements) => {
        const existingIds = new Set(currentElements.map((el) => el.data?.id));
        const kept = currentElements.filter((el) => {
          if (!el.data) return true;
          if (el.data.id === nodeId) return false;
          if (el.data.source === nodeId || el.data.target === nodeId) return false;
          return true;
        });

        const newNodes = expansion.nodes
          .filter((node) => !existingIds.has(node.id))
          .map((node) => ({
            data: {
              ...node,
              id: node.id,
              label: node.label,
              displayLabel: node.label
            }
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
              label: edge.edge_type === 'summary_edge'
                ? edge.label
                : `${edge.from_column} → ${edge.to_column}`
            }
          }));

        return [...kept, ...newNodes, ...newEdges];
      });

      logFrontendEvent('summary_node_expand_success', `Expanded summary node: ${nodeId}`, { nodeId, expanded_node_count: expansion.nodes.length, edge_count: expansion.edges.length });
      setMessage(`已展開 ${nodeData.label}：${expansion.nodes.length} table(s)。`);
    } catch (err) {
      logFrontendEvent('summary_node_expand_error', err.message, { nodeId });
      setMessage(`展開 summary node 失敗：${err.message}`);
    }
  };

  const handleCyReady = useCallback((cy) => {
    cyRef.current = cy;

    cy.on('tap', 'node', (event) => {
      const node = event.target;
      const data = node.data();

      markSelectedNode(data.id);

      if (data.node_type === 'summary') {
        expandSummaryNode(data.id, data);
      } else {
        logFrontendEvent('table_node_click', `User clicked table node: ${data.id}`, { table: data.id });
      fetchTableDetail(data.id);
      }
    });

    cy.on('mouseover', 'edge', (event) => {
      event.target.select();
    });

    cy.on('mouseout', 'edge', (event) => {
      event.target.unselect();
    });
  }, [markSelectedNode, fetchTableDetail, databaseInfo, selectedTable, currentFocusTable, focusDepth, elements]);

  const handleSearchChange = (event) => {
    const tableName = event.target.value;
    setSelectedTable(tableName);
    logFrontendEvent('table_select_change', `User selected table: ${tableName}`, { table: tableName });

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
    logFrontendEvent('full_graph_click', 'User switched to full graph', { node_count: fullGraph.node_count, edge_count: fullGraph.edge_count });
    renderFullGraph(fullGraph);
    setCurrentFocusTable('');
    setMessage(`已切回完整 graph：${fullGraph.node_count} tables, ${fullGraph.edge_count} foreign keys。`);
  };

  const handleDepthChange = (event) => {
    const depth = Number(event.target.value);
    logFrontendEvent('depth_change', `User changed focus depth to ${depth}`, { depth });
    setFocusDepth(depth);

    if (viewMode === 'summary' && currentFocusTable) {
      pushCurrentGraphState();
      renderFocusSummaryGraph(currentFocusTable, depth);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>SchemaLens</h1>
        <p className="subtitle">Cytoscape Schema Graph Viewer</p>

        <label className="upload-box">
          <input type="file" accept=".db,.sqlite,.sqlite3" onChange={handleUpload} disabled={loading} />
          {loading ? '處理中...' : '上傳 SQLite .db'}
        </label>

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

        {tableNames.length > 0 && (
          <>
            <label className="field-label">搜尋 / 選擇 focus table</label>
            <select className="select" value={selectedTable} onChange={handleSearchChange}>
              <option value="">選擇 table</option>
              {tableNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>

            <label className="field-label">Focus depth</label>
            <select className="select" value={focusDepth} onChange={handleDepthChange}>
              <option value={1}>1-hop neighbors</option>
              <option value={2}>2-hop neighbors</option>
              <option value={3}>3-hop neighbors</option>
            </select>

            <div className="button-row">
              <button className="secondary-button" onClick={handleSummaryButton}>Summary View</button>
              <button className="secondary-button" onClick={handleFullGraphButton}>Full Graph</button>
            </div>

            <button
              className="secondary-button"
              onClick={restorePreviousStep}
              disabled={graphHistory.length === 0}
              title={graphHistory.length === 0 ? '目前沒有上一步' : '回到上一個 graph 狀態'}
            >
              回到上一步
            </button>
          </>
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
            <div className="detail-row">Rows: {tableDetail.table.row_count ?? '?'}</div>
            <div className="detail-row">PK: {tableDetail.table.primary_keys.join(', ') || 'None'}</div>

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
            {tableDetail.table.foreign_keys.length === 0 ? (
              <p className="muted">No outgoing foreign keys.</p>
            ) : (
              tableDetail.table.foreign_keys.map((fk, index) => (
                <div key={`${fk.from_column}-${index}`} className="fk-item">
                  {fk.from_column} → {fk.table}.{fk.to_column}
                </div>
              ))
            )}

            <h3>Referenced by</h3>
            {tableDetail.referenced_by.length === 0 ? (
              <p className="muted">No incoming references.</p>
            ) : (
              tableDetail.referenced_by.map((edge) => (
                <div key={edge.id} className="fk-item">
                  {edge.source}.{edge.from_column} → {edge.target}.{edge.to_column}
                </div>
              ))
            )}
          </div>
        )}
      </aside>

      <main className="graph-area">
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