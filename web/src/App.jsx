import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const ORDER = [
  'dashboard.send.click',
  'dashboard.request.sent',
  'gateway.message.received',
  'gateway.processing.start',
  'provider.request.start',
  'provider.first_token',
  'provider.response.complete',
  'dashboard.push.start',
  'dashboard.render.done',
];

const SEGMENT_META = {
  'T1-T0': { from: 0, to: 1 },
  'T2-T1': { from: 1, to: 2 },
  'T3-T2': { from: 2, to: 3 },
  'T4-T3': { from: 3, to: 4 },
  'T5-T4': { from: 4, to: 5 },
  'T6-T5': { from: 5, to: 6 },
  'T7-T6': { from: 6, to: 7 },
  'T8-T7': { from: 7, to: 8 },
};

function useTraceSocket(url) {
  const [traces, setTraces] = useState([]);
  const [status, setStatus] = useState('connecting');
  const [sourceLogFile, setSourceLogFile] = useState('-');
  const retryRef = useRef(null);

  useEffect(() => {
    let ws;
    let closedByUser = false;

    const connect = () => {
      setStatus('connecting');
      ws = new WebSocket(url);

      ws.onopen = () => setStatus('connected');
      ws.onclose = () => {
        if (closedByUser) return;
        setStatus('reconnecting');
        retryRef.current = setTimeout(connect, 1200);
      };
      ws.onerror = () => setStatus('error');

      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.meta?.logFile) {
          setSourceLogFile(msg.meta.logFile);
        }
        if (msg.type === 'snapshot') {
          setTraces(msg.data || []);
        }
        if (msg.type === 'trace_update') {
          setTraces((prev) => [msg.data, ...prev].slice(0, 100));
        }
      };
    };

    connect();

    return () => {
      closedByUser = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      if (ws) ws.close();
    };
  }, [url]);

  return { traces, status, sourceLogFile };
}

function toFlow(result) {
  const slowest = result.slowest?.key;
  const nodes = ORDER.map((event, idx) => ({
    id: event,
    position: { x: 70 + idx * 220, y: 140 },
    data: { label: event },
    style: {
      border: '1px solid #666',
      borderRadius: 10,
      width: 190,
      fontSize: 12,
      padding: 10,
      background: '#111827',
      color: 'white',
    },
  }));

  const segMap = Object.fromEntries((result.segments || []).map((s) => [s.key, s]));
  const edges = Object.entries(SEGMENT_META).map(([key, meta]) => {
    const seg = segMap[key];
    const isSlow = key === slowest;
    const label = `${key}: ${seg?.ms == null ? 'missing' : `${seg.ms.toFixed(2)} ms`}`;
    return {
      id: key,
      source: ORDER[meta.from],
      target: ORDER[meta.to],
      label,
      animated: isSlow,
      style: { stroke: isSlow ? '#ef4444' : '#60a5fa', strokeWidth: isSlow ? 3 : 2 },
      labelStyle: { fill: isSlow ? '#ef4444' : '#93c5fd', fontSize: 12, fontWeight: 700 },
    };
  });

  return { nodes, edges };
}

export default function App() {
  const { traces, status, sourceLogFile } = useTraceSocket('ws://127.0.0.1:8765');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (!selected && traces.length > 0) {
      setSelected(traces[0]);
    }
  }, [traces, selected]);

  const current = selected || traces[0] || null;
  const flow = useMemo(() => (current ? toFlow(current) : { nodes: [], edges: [] }), [current]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>最近消息</h3>
        <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>WS: {status}</div>
        <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 12 }}>source: {sourceLogFile}</div>
        {traces.map((t, idx) => (
          <button key={`${t.traceId}-${idx}`} onClick={() => setSelected(t)} className="trace-item">
            <div>{t.traceId}</div>
            <small>T8-T0: {(t.segments?.find((s) => s.key === 'T8-T0')?.ms ?? 'missing')}</small>
          </button>
        ))}
      </aside>

      <main className="main">
        <header className="summary">
          <div><b>traceId:</b> {current?.traceId || '-'}</div>
          <div><b>最慢环节:</b> {current?.slowest?.key || 'missing'}</div>
          <div><b>最慢占比:</b> {current?.slowest?.ratio_pct == null ? 'missing' : `${current.slowest.ratio_pct}%`}</div>
          <div><b>原因提示:</b> {current?.slowest?.hint || 'missing'}</div>
        </header>

        <div className="flow-wrap">
          <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </main>
    </div>
  );
}
