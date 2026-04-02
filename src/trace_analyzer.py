#!/usr/bin/env python3
"""OpenClaw 单条消息全链路时序追踪（MVP）"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


REQUIRED_EVENTS = [
    "dashboard.send.click",      # T0
    "dashboard.request.sent",    # T1
    "gateway.message.received",  # T2
    "gateway.processing.start",  # T3
    "provider.request.start",    # T4
    "provider.first_token",      # T5
    "provider.response.complete",# T6
    "dashboard.push.start",      # T7
    "dashboard.render.done",     # T8
]

EVENT_TO_T = {name: f"T{i}" for i, name in enumerate(REQUIRED_EVENTS)}

SEGMENTS: List[Tuple[str, str, str, str]] = [
    ("T1-T0", "dashboard.request.sent", "dashboard.send.click", "前端发送耗时"),
    ("T2-T1", "gateway.message.received", "dashboard.request.sent", "前端到网关入口延迟"),
    ("T3-T2", "gateway.processing.start", "gateway.message.received", "网关排队/进入处理延迟"),
    ("T4-T3", "provider.request.start", "gateway.processing.start", "网关内部准备时间"),
    ("T5-T4", "provider.first_token", "provider.request.start", "首响应等待时间"),
    ("T6-T5", "provider.response.complete", "provider.first_token", "模型持续输出时间"),
    ("T7-T6", "dashboard.push.start", "provider.response.complete", "回推准备时间"),
    ("T8-T7", "dashboard.render.done", "dashboard.push.start", "页面显示完成时间"),
    ("T5-T0", "provider.first_token", "dashboard.send.click", "首响应总时间"),
    ("T8-T0", "dashboard.render.done", "dashboard.send.click", "全链路总耗时"),
]

CAUSE_HINTS = {
    "T1-T0": "前端主线程繁忙、序列化或网络栈阻塞。",
    "T2-T1": "客户端到网关网络抖动、TLS/连接复用问题。",
    "T3-T2": "网关排队长度高、并发限制或线程池饱和。",
    "T4-T3": "网关鉴权、路由、上下文拼装或缓存 miss。",
    "T5-T4": "上游模型排队、冷启动、首 token 生成慢。",
    "T6-T5": "模型推理速度慢、输出 token 多或限速。",
    "T7-T6": "网关流转收尾、消息持久化或推送队列等待。",
    "T8-T7": "前端渲染阻塞、DOM diff/大组件重绘。",
    "T5-T0": "首包链路长：前端/网关/模型任一关键路径偏慢。",
    "T8-T0": "端到端总链路长：需优先优化最慢阶段。",
}

RED = "\033[91m"
RESET = "\033[0m"


@dataclass
class SegmentResult:
    key: str
    label: str
    ms: Optional[float]


def parse_ts(ts: str) -> datetime:
    normalized = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_trace(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_event_map(events: List[Dict]) -> Dict[str, datetime]:
    latest: Dict[str, datetime] = {}
    for e in events:
        name = e.get("name")
        ts = e.get("timestamp")
        if name in REQUIRED_EVENTS and ts:
            latest[name] = parse_ts(ts)
    return latest


def calc_ms(end: Optional[datetime], start: Optional[datetime]) -> Optional[float]:
    if end is None or start is None:
        return None
    return round((end - start).total_seconds() * 1000, 2)


def analyze(trace: Dict) -> Dict:
    trace_id = trace.get("traceId", "missing")
    event_map = build_event_map(trace.get("events", []))

    missing_events = [f"{EVENT_TO_T[e]}={e}" for e in REQUIRED_EVENTS if e not in event_map]

    results: List[SegmentResult] = []
    for key, end_name, start_name, label in SEGMENTS:
        ms = calc_ms(event_map.get(end_name), event_map.get(start_name))
        results.append(SegmentResult(key=key, label=label, ms=ms))

    candidates = [r for r in results if r.ms is not None and r.key not in ("T5-T0", "T8-T0")]
    slowest = max(candidates, key=lambda x: x.ms) if candidates else None

    total = next((r.ms for r in results if r.key == "T8-T0"), None)
    slowest_ratio = round((slowest.ms / total) * 100, 2) if slowest and total else None

    return {
        "traceId": trace_id,
        "missing": missing_events,
        "segments": results,
        "slowest": {
            "key": slowest.key,
            "label": slowest.label,
            "ms": slowest.ms,
            "ratio_pct": slowest_ratio,
            "hint": CAUSE_HINTS.get(slowest.key, "建议结合上下游日志进一步定位。"),
        } if slowest else None,
    }


def fmt(ms: Optional[float]) -> str:
    return "missing" if ms is None else f"{ms:.2f} ms"


def print_report(result: Dict) -> None:
    print(f"traceId: {result['traceId']}")
    if result["missing"]:
        print("missing events:")
        for m in result["missing"]:
            print(f"  - {m}")

    slowest_key = result["slowest"]["key"] if result["slowest"] else None
    print("\nsegments:")
    for seg in result["segments"]:
        line = f"  {seg.key:<5} | {seg.label:<18} | {fmt(seg.ms)}"
        if seg.key == slowest_key:
            print(f"{RED}{line}  <-- slowest{RESET}")
        else:
            print(line)

    print("\nslowest summary:")
    if not result["slowest"]:
        print("  missing")
        return

    s = result["slowest"]
    ratio = "missing" if s["ratio_pct"] is None else f"{s['ratio_pct']:.2f}%"
    print(f"  key: {s['key']}")
    print(f"  duration: {fmt(s['ms'])}")
    print(f"  ratio: {ratio}")
    print(f"  hint: {s['hint']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze OpenClaw single-message latency trace")
    parser.add_argument("trace_file", help="Path to trace json file")
    args = parser.parse_args()

    trace = load_trace(args.trace_file)
    result = analyze(trace)
    print_report(result)


if __name__ == "__main__":
    main()
