#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import md5
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

INFER_RULES = [
    ("dashboard.send.click", "dashboard.send.click"),
    ("dashboard.request.sent", "dashboard.request.sent"),
    ("gateway.message.received", "gateway.message.received"),
    ("gateway.processing.start", "gateway.processing.start"),
    ("provider.request.start", "provider.request.start"),
    ("provider.first_token", "provider.first_token"),
    ("provider.response.complete", "provider.response.complete"),
    ("dashboard.push.start", "dashboard.push.start"),
    ("dashboard.render.done", "dashboard.render.done"),
    ("first token", "provider.first_token"),
    ("response complete", "provider.response.complete"),
]


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


def _infer_event(merged: Dict[str, Any]) -> Optional[str]:
    event = merged.get("event") or merged.get("name") or merged.get("stage")
    meta = merged.get("_meta") if isinstance(merged.get("_meta"), dict) else {}
    if not event:
        event = meta.get("event") or meta.get("event_name") or meta.get("stage")

    if isinstance(event, str):
        return EVENT_ALIASES.get(event, event)

    # 真实日志可能是 {"0":"...","1":"...","_meta":...,"time":"..."}
    text_parts = []
    for k, v in merged.items():
        if isinstance(v, str):
            text_parts.append(v)
    hay = " ".join(text_parts).lower()
    for keyword, normalized in INFER_RULES:
        if keyword in hay:
            return normalized
    return None


def _extract_trace_id(merged: Dict[str, Any]) -> str:
    meta = merged.get("_meta") if isinstance(merged.get("_meta"), dict) else {}

    trace_id = (
        merged.get("traceId")
        or merged.get("trace_id")
        or merged.get("x_trace_id")
        or merged.get("x-trace-id")
        or meta.get("traceId")
        or meta.get("trace_id")
        or meta.get("x_trace_id")
        or meta.get("x-trace-id")
    )

    headers = merged.get("headers") if isinstance(merged.get("headers"), dict) else {}
    if not trace_id:
        trace_id = headers.get("x-trace-id") or headers.get("x_trace_id")

    if trace_id:
        return str(trace_id)

    # 没有直接 traceId：尝试 request_id / message_id / conversation_id 生成关联ID
    fallback_seed = (
        str(meta.get("request_id") or "")
        + "|"
        + str(meta.get("message_id") or "")
        + "|"
        + str(meta.get("conversation_id") or "")
    )
    if fallback_seed != "||":
        return "derived-" + md5(fallback_seed.encode("utf-8")).hexdigest()[:16]

    return "missing"


def adapt_raw_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    merged = dict(raw)
    message_obj = _as_dict(raw.get("message"))
    if message_obj:
        merged.update(message_obj)

    ts = merged.get("ts") or merged.get("timestamp") or merged.get("time") or merged.get("@timestamp")
    event = _infer_event(merged)
    if not event:
        return None

    trace_id = _extract_trace_id(merged)
    module = merged.get("module") or merged.get("service") or ((merged.get("_meta") or {}).get("module") if isinstance(merged.get("_meta"), dict) else None) or "unknown"

    return {
        "ts": ts or utc_now_iso(),
        "traceId": trace_id,
        "event": event,
        "module": module,
        "raw": raw,
    }
