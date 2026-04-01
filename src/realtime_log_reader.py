#!/usr/bin/env python3
"""实时日志读取器（MVP）

- 持续 tail JSONL 日志
- 按 traceId 聚合事件
- 调用 trace_analyzer.analyze 输出结果
- 缺字段稳健处理，不崩溃
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trace_analyzer import REQUIRED_EVENTS, analyze, print_report


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_event(raw: Dict) -> Optional[Dict]:
    ts = raw.get("ts") or raw.get("timestamp")
    event = raw.get("event") or raw.get("name")
    trace_id = raw.get("traceId")

    if not event:
        return None

    return {
        "name": event,
        "timestamp": ts or utc_now_iso(),
        "traceId": trace_id or "missing",
        "raw": raw,
    }


@dataclass
class TraceBuffer:
    trace_id: str
    events: List[Dict] = field(default_factory=list)
    seen: set = field(default_factory=set)
    last_update: float = field(default_factory=time.time)

    def add(self, ev: Dict) -> None:
        self.events.append({"name": ev["name"], "timestamp": ev["timestamp"]})
        self.seen.add(ev["name"])
        self.last_update = time.time()

    def ready(self) -> bool:
        return "dashboard.render.done" in self.seen or all(e in self.seen for e in REQUIRED_EVENTS)


def parse_line(line: str) -> Optional[Dict]:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return normalize_event(data)


def process_file(log_path: str, idle_flush_sec: int = 30, poll_interval: float = 0.5) -> None:
    traces: Dict[str, TraceBuffer] = {}

    with open(log_path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        print(f"[reader] tailing: {log_path}", flush=True)

        while True:
            line = f.readline()
            if not line:
                now = time.time()
                stale = [tid for tid, b in traces.items() if now - b.last_update >= idle_flush_sec]
                for tid in stale:
                    buf = traces.pop(tid)
                    result = analyze({"traceId": tid, "events": buf.events})
                    print("\n[reader] idle flush", flush=True)
                    print_report(result)
                time.sleep(poll_interval)
                continue

            ev = parse_line(line)
            if ev is None:
                continue

            tid = ev["traceId"]
            if tid == "missing":
                continue

            buf = traces.setdefault(tid, TraceBuffer(trace_id=tid))
            buf.add(ev)

            if buf.ready():
                result = analyze({"traceId": tid, "events": buf.events})
                print("\n[reader] trace complete", flush=True)
                print_report(result)
                traces.pop(tid, None)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Tail OpenClaw JSONL logs and analyze traces")
    parser.add_argument("log_file", help="Path to JSONL log file")
    parser.add_argument("--idle-flush-sec", type=int, default=30, help="Flush inactive trace buffers")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="File tail poll interval")
    args = parser.parse_args()

    process_file(args.log_file, idle_flush_sec=args.idle_flush_sec, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
