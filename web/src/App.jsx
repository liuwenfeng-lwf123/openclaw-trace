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

function useTraceSocket(url, onUpsert) {
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
        console.log('[ui-ws] payload', msg);
        if (msg.meta?.logFile) setSourceLogFile(msg.meta.logFile);

        if (msg.type === 'snapshot') {
          setTraces(msg.data || []);
          console.log('[ui-state] recent list size', (msg.data || []).length);
          return;
        }

        if (msg.type === 'trace_update') {
          setTraces((prev) => {
            const key = msg.data?.traceId;
            const filtered = prev.filter((x) => x.traceId !== key);
            const next = [msg.data, ...filtered].slice(0, 100);
            console.log('[ui-state] recent list size', next.length);
            onUpsert?.(key);
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
  }, [url, onUpsert]);

  return { traces, status, sourceLogFile };
}

function toFlow(result) {
  const slowest = result.slowest?.key;
  const status = result.status || 'ok';
  const segMap = Object.fromEntries((result.segments || []).map((s) => [s.key, s]));

  const nodes = ORDER.map((event, idx) => {
    const missing = (result.missing || []).some((m) => m.includes(event));
    return {
      id: event,
      position: { x: 90 + idx * 300, y: 110 + (idx % 2) * 120 },
      data: { label: `${event}${missing ? ' (missing)' : ''}` },
      style: {
        border: `1px solid ${missing ? '#f59e0b' : '#4b5563'}`,
        borderRadius: 12,
        width: 240,
        fontSize: 12,
        padding: 12,
        background: status === 'timeout' ? '#3f1d1d' : '#0f172a',
        color: 'white',
      },
    };
  });

  const edges = Object.entries(SEGMENT_META).map(([key, meta]) => {
    const seg = segMap[key];
    const isSlow = key === slowest;
    const isMissing = seg?.ms == null;
    const label = `${key}  ${isMissing ? 'missing' : `${seg.ms.toFixed(2)} ms`}`;
    return {
      id: key,
      source: ORDER[meta.from],
      target: ORDER[meta.to],
      label,
      animated: isSlow,
      style: { stroke: isSlow ? '#ef4444' : isMissing ? '#f59e0b' : '#60a5fa', strokeWidth: isSlow ? 3 : 2 },
      labelStyle: { fill: isSlow ? '#ef4444' : isMissing ? '#f59e0b' : '#cbd5e1', fontSize: 12, fontWeight: 700 },
      labelBgStyle: { fill: '#0b1228', fillOpacity: 0.95 },
      labelBgPadding: [6, 4],
      labelBgBorderRadius: 6,
    };
  });

  return { nodes, edges };
}

function fmt(val) {
  return val == null ? 'missing' : `${val.toFixed(2)} ms`;
}

export default function App() {
  const [selectedTraceId, setSelectedTraceId] = useState(null);
  const { traces, status, sourceLogFile } = useTraceSocket('ws://127.0.0.1:8765', (id) => {
    if (id) setSelectedTraceId(id);
  });

  useEffect(() => {
    if (selectedTraceId) console.log('[ui-state] selected trace id', selectedTraceId);
  }, [selectedTraceId]);

  const current = traces.find((t) => t.traceId === selectedTraceId) || traces[0] || null;
  const flow = useMemo(() => (current ? toFlow(current) : { nodes: [], edges: [] }), [current]);

  const segMap = useMemo(() => {
    if (!current?.segments) return {};
    return Object.fromEntries(current.segments.map((s) => [s.key, s]));
  }, [current]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>最近消息</h3>
        <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>WS: {status}</div>
        <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 12 }}>source: {sourceLogFile}</div>
        {traces.length === 0 && <div style={{fontSize:12,opacity:0.8}}>暂无记录，检查 reader-debug 的 line_parsed_ok</div>}
        {traces.map((t, idx) => (
          <button key={`${t.traceId}-${idx}`} onClick={() => setSelectedTraceId(t.traceId)} className="trace-item">
            <div>{t.traceId}</div>
            <small>
              status={t.status || 'ok'}{t.partial ? ' (partial)' : ''} | T8-T0: {(t.segments?.find((s) => s.key === 'T8-T0')?.ms ?? 'missing')}
            </small>
          </button>
        ))}
      </aside>

      <main className="main">
        <header className="summary">
          <div><b>ID:</b> {current?.traceId || '-'} ({current?.group_key_type || 'unknown'})</div>
          <div><b>status:</b> {current?.status || '-'} {current?.error_reason ? `| ${current.error_reason}` : ''}</div>
          <div><b>provider/model:</b> {(current?.provider || '-') + ' / ' + (current?.model || '-')}</div>
          {current?.partial ? (
            <div><b>实时耗时:</b> collecting...</div>
          ) : (
            <>
              <div><b>首 token:</b> {fmt(segMap['T5-T0']?.ms)}</div>
              <div><b>总耗时:</b> {fmt(segMap['T8-T0']?.ms)}</div>
              <div><b>最慢环节:</b> {current?.slowest?.key || 'missing'}</div>
              <div><b>最慢占比:</b> {current?.slowest?.ratio_pct == null ? 'missing' : `${current.slowest.ratio_pct}%`}</div>
              <div style={{ gridColumn: '1 / span 2' }}><b>原因提示:</b> {current?.slowest?.hint || 'missing'}</div>
            </>
          )}
        </header>

        <div style={{ maxHeight: 150, overflow: 'auto', fontSize: 12, padding: '0 12px' }}>
          <b>events timeline:</b>
          <ul>
            {(current?.event_timeline || []).map((e, i) => (
              <li key={`${e.ts}-${i}`}>{e.ts} | {e.event} | {e.module} {e.error ? `| error=${e.error}` : ''}</li>
            ))}
          </ul>
        </div>

        <div className="flow-wrap">
          <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView fitViewOptions={{ padding: 0.25 }}>
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </main>
    </div>
  );
}
