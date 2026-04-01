#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import md5
from typing import Any, Dict, Optional, Tuple

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

KEY_PRIORITY = [
    "traceId", "trace_id", "x_trace_id", "x-trace-id",
    "runId", "_meta.request_id", "message_id", "conversation_id",
]


SPECIAL_TEXT_EVENTS = [
    "model_fallback_decision",
    "embedded_run_agent_end",
    "live session model switch",
    "recall failed",
    "timeout",
    "rate limit",
    "http 401",
    "econnrefused",
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


def _read_nested(merged: Dict[str, Any], key: str) -> Optional[str]:
    if "." not in key:
        v = merged.get(key)
        return str(v) if v not in (None, "") else None

    first, second = key.split(".", 1)
    container = merged.get(first)
    if isinstance(container, dict):
        v = container.get(second)
        return str(v) if v not in (None, "") else None
    return None


def _normalize_event_name(ev: str) -> str:
    lowered = ev.lower().strip()
    return EVENT_ALIASES.get(lowered, ev)


def _extract_event_and_attrs(merged: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    attrs: Dict[str, Any] = {}

    payload1 = merged.get("1")
    if isinstance(payload1, dict):
        event = payload1.get("event")
        attrs["runId"] = payload1.get("runId")
        attrs["tags"] = payload1.get("tags")
        attrs["error"] = payload1.get("error")
        attrs["provider"] = payload1.get("provider")
        attrs["model"] = payload1.get("model")
        if isinstance(event, str) and event:
            return _normalize_event_name(event), attrs

    # 优先字段
    event = merged.get("event") or merged.get("name") or merged.get("stage")
    meta = merged.get("_meta") if isinstance(merged.get("_meta"), dict) else {}
    if not event:
        event = meta.get("event") or meta.get("event_name") or meta.get("stage")
    if isinstance(event, str) and event:
        return _normalize_event_name(event), attrs

    # 1 是字符串时，做文本匹配
    text_parts = []
    for _, v in merged.items():
        if isinstance(v, str):
            text_parts.append(v)
    hay = " ".join(text_parts).lower()

    for special in SPECIAL_TEXT_EVENTS:
        if special in hay:
            return special, attrs

    return None, attrs


def _extract_group_key(merged: Dict[str, Any], attrs: Dict[str, Any]) -> Tuple[str, str]:
    merged = dict(merged)
    if attrs.get("runId"):
        merged["runId"] = attrs.get("runId")

    for key in KEY_PRIORITY:
        v = _read_nested(merged, key)
        if v:
            return key, v

    fallback_seed = "|".join([
        str(_read_nested(merged, "_meta.request_id") or ""),
        str(_read_nested(merged, "message_id") or ""),
        str(_read_nested(merged, "conversation_id") or ""),
    ])
    if fallback_seed != "||":
        return "derived", "derived-" + md5(fallback_seed.encode("utf-8")).hexdigest()[:16]

    return "missing", "missing"


def adapt_raw_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    merged = dict(raw)
    message_obj = _as_dict(raw.get("message"))
    if message_obj:
        merged.update(message_obj)

    ts = merged.get("ts") or merged.get("timestamp") or merged.get("time") or merged.get("@timestamp")
    event, attrs = _extract_event_and_attrs(merged)
    if not event:
        return None

    key_type, group_id = _extract_group_key(merged, attrs)

    meta = merged.get("_meta") if isinstance(merged.get("_meta"), dict) else {}
    module = merged.get("module") or merged.get("service") or meta.get("module") or "unknown"
    provider = attrs.get("provider") or merged.get("provider") or meta.get("provider")
    model = attrs.get("model") or merged.get("model") or meta.get("model")
    error = attrs.get("error") or merged.get("error") or meta.get("error")

    return {
        "ts": ts or utc_now_iso(),
        "traceId": group_id,
        "groupKeyType": key_type,
        "event": event,
        "module": module,
        "provider": provider,
        "model": model,
        "error": error,
        "tags": attrs.get("tags"),
        "raw": raw,
    }
