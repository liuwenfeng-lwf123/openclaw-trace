#!/usr/bin/env python3
"""将真实 OpenClaw 运行日志适配为标准事件:
{ts, traceId, event, module}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


EVENT_ALIASES = {
    "send_click": "dashboard.send.click",
    "request_sent": "dashboard.request.sent",
    "message_received": "gateway.message.received",
    "processing_start": "gateway.processing.start",
    "provider_request_start": "provider.request.start",
    "first_token": "provider.first_token",
    "response_complete": "provider.response.complete",
    "push_start": "dashboard.push.start",
    "render_done": "dashboard.render.done",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("{") and v.endswith("}"):
            try:
                obj = json.loads(v)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return None
    return None


def adapt_raw_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把多种 OpenClaw 运行日志结构归一化为标准事件。"""

    merged = dict(raw)
    message_obj = _as_dict(raw.get("message"))
    if message_obj:
        merged.update(message_obj)

    ts = merged.get("ts") or merged.get("timestamp") or merged.get("time") or merged.get("@timestamp")

    trace_id = (
        merged.get("traceId")
        or merged.get("trace_id")
        or merged.get("x_trace_id")
        or merged.get("x-trace-id")
    )

    headers = merged.get("headers") if isinstance(merged.get("headers"), dict) else {}
    if not trace_id:
        trace_id = headers.get("x-trace-id") or headers.get("x_trace_id")

    event = merged.get("event") or merged.get("name") or merged.get("stage")
    if isinstance(event, str):
        event = EVENT_ALIASES.get(event, event)

    module = merged.get("module") or merged.get("service") or "unknown"

    if not event:
        return None

    return {
        "ts": ts or utc_now_iso(),
        "traceId": trace_id or "missing",
        "event": event,
        "module": module,
        "raw": raw,
    }
