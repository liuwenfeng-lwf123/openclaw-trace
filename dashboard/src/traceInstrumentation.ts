/**
 * OpenClaw Dashboard 最小埋点实现（MVP）
 * 输出 JSONL 字段统一为: { ts, traceId, event, module }
 */

export type TraceEvent = {
  ts: string;
  traceId: string;
  event: string;
  module: string;
};

const MODULE = "dashboard";

function nowIso(): string {
  return new Date().toISOString();
}

export function emitTraceEvent(traceId: string, event: string): void {
  const payload: TraceEvent = {
    ts: nowIso(),
    traceId,
    event,
    module: MODULE,
  };

  // 最小改动：先打到 console，生产中由日志采集器收集为 JSONL
  console.log(JSON.stringify(payload));
}

export function onSendClick(traceId: string): void {
  // T0 = dashboard.send.click
  emitTraceEvent(traceId, "dashboard.send.click");
}

export async function sendRequest(traceId: string, url: string, body: unknown): Promise<Response> {
  // T1 = dashboard.request.sent
  emitTraceEvent(traceId, "dashboard.request.sent");
  return fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-trace-id": traceId,
    },
    body: JSON.stringify({ ...(body as Record<string, unknown>), traceId }),
  });
}

export function onPushStart(traceId: string): void {
  // T7 = dashboard.push.start
  emitTraceEvent(traceId, "dashboard.push.start");
}

export function onRenderDone(traceId: string): void {
  // T8 = dashboard.render.done
  emitTraceEvent(traceId, "dashboard.render.done");
}
