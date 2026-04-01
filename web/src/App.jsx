import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const ORDER = [
  'dashboard.send.click', 'dashboard.request.sent', 'gateway.message.received', 'gateway.processing.start',
  'provider.request.start', 'provider.first_token', 'provider.response.complete', 'dashboard.push.start', 'dashboard.render.done',
];

const SEGMENT_META = {
  'T1-T0': { from: 0, to: 1 }, 'T2-T1': { from: 1, to: 2 }, 'T3-T2': { from: 2, to: 3 }, 'T4-T3': { from: 3, to: 4 },
  'T5-T4': { from: 4, to: 5 }, 'T6-T5': { from: 5, to: 6 }, 'T7-T6': { from: 6, to: 7 }, 'T8-T7': { from: 7, to: 8 },
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
      console.log('[ui-ws] connecting', { url });
      setStatus('connecting');
      ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('[ui-ws] connected');
        setStatus('connected');
      };

      ws.onclose = (evt) => {
        console.log('[ui-ws] closed', { code: evt.code, reason: evt.reason });
        if (closedByUser) return;
        setStatus('reconnecting');
        retryRef.current = setTimeout(connect, 1200);
      };

      ws.onerror = (err) => {
        console.log('[ui-ws] error', err);
        setStatus('error');
      };

      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        console.log('[ui-ws] payload', msg);

        if (msg.meta?.logFile) setSourceLogFile(msg.meta.logFile);

        if (msg.type === 'snapshot') {
          setTraces(msg.data || []);
          console.log('[ui-state] snapshot_update', { count: (msg.data || []).length });
        }

        if (msg.type === 'trace_update') {
          setTraces((prev) => {
            const next = [msg.data, ...prev].slice(0, 100);
            console.log('[ui-state] trace_update', { traceId: msg.data?.traceId, count: next.length });
            return next;
          });
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
  const status = result.status || 'ok';

  const nodes = ORDER.map((event, idx) => {
    const missing = (result.missing || []).some((m) => m.includes(event));
    return {
      id: event,
      position: { x: 70 + idx * 220, y: 140 },
      data: { label: `${event}${missing ? ' (missing)' : ''}` },
      style: {
        border: `1px solid ${missing ? '#f59e0b' : '#666'}`,
        borderRadius: 10,
        width: 190,
        fontSize: 12,
        padding: 10,
        background: status === 'timeout' ? '#3f1d1d' : '#111827',
        color: 'white',
      },
    };
  });

  const segMap = Object.fromEntries((result.segments || []).map((s) => [s.key, s]));
  const edges = Object.entries(SEGMENT_META).map(([key, meta]) => {
    const seg = segMap[key];
    const isSlow = key === slowest;
    const isMissing = seg?.ms == null;
    const label = `${key}: ${isMissing ? 'missing' : `${seg.ms.toFixed(2)} ms`}`;
    return {
      id: key,
      source: ORDER[meta.from],
      target: ORDER[meta.to],
      label,
      animated: isSlow,
      style: {
        stroke: isSlow ? '#ef4444' : isMissing ? '#f59e0b' : '#60a5fa',
        strokeWidth: isSlow ? 3 : 2,
      },
      labelStyle: { fill: isSlow ? '#ef4444' : isMissing ? '#f59e0b' : '#93c5fd', fontSize: 12, fontWeight: 700 },
    };
  });

  return { nodes, edges };
}

export default function App() {
  const { traces, status, sourceLogFile } = useTraceSocket('ws://127.0.0.1:8765');
  const [selectedTraceId, setSelectedTraceId] = useState(null);

  // 默认自动选中最新消息
  useEffect(() => {
    if (traces.length > 0) {
      setSelectedTraceId(traces[0].traceId);
      console.log('[ui-state] auto_select_latest', traces[0].traceId);
    }
  }, [traces]);

  const current = traces.find((t) => t.traceId === selectedTraceId) || traces[0] || null;
  const flow = useMemo(() => (current ? toFlow(current) : { nodes: [], edges: [] }), [current]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>最近消息</h3>
        <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>WS: {status}</div>
        <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 12 }}>source: {sourceLogFile}</div>
        {traces.map((t, idx) => (
          <button key={`${t.traceId}-${idx}`} onClick={() => setSelectedTraceId(t.traceId)} className="trace-item">
            <div>{t.traceId}</div>
            <small>
              status={t.status || 'ok'} | T8-T0: {(t.segments?.find((s) => s.key === 'T8-T0')?.ms ?? 'missing')}
            </small>
          </button>
        ))}
      </aside>

      <main className="main">
        <header className="summary">
          <div><b>traceId:</b> {current?.traceId || '-'}</div>
          <div><b>status:</b> {current?.status || '-'}</div>
          <div><b>最慢环节:</b> {current?.slowest?.key || 'missing'}</div>
          <div><b>最慢占比:</b> {current?.slowest?.ratio_pct == null ? 'missing' : `${current.slowest.ratio_pct}%`}</div>
          <div style={{ gridColumn: '1 / span 2' }}><b>原因提示:</b> {current?.slowest?.hint || 'missing'}</div>
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
