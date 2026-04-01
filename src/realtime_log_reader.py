#!/usr/bin/env python3
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
from typing import Callable, Dict, Generator, List, Optional, Tuple

from openclaw_event_adapter import adapt_raw_event
from trace_analyzer import REQUIRED_EVENTS, analyze, print_report

AnalyzeCallback = Callable[[Dict], None]
DEBUG = os.getenv("OPENCLAW_TRACE_DEBUG", "1") == "1"


def dlog(msg: str) -> None:
    if DEBUG:
        print(f"[reader-debug] {msg}", flush=True)


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


def parse_line(line: str) -> Tuple[Optional[Dict], Optional[str]]:
    raw_line = line.strip()
    if not raw_line:
        return None, "empty_line"

    # 支持日志前缀 + JSON 场景，尝试截取第一个 JSON 对象
    json_part = raw_line
    if not raw_line.startswith("{"):
        pos = raw_line.find("{")
        if pos >= 0:
            json_part = raw_line[pos:]

    try:
        data = json.loads(json_part)
    except json.JSONDecodeError:
        return None, "invalid_json"

    if not isinstance(data, dict):
        return None, "not_dict"

    normalized = adapt_raw_event(data)
    if not normalized:
        return None, "adapter_no_event"

    event = {
        "name": normalized["event"],
        "timestamp": normalized["ts"],
        "traceId": normalized["traceId"],
        "raw": normalized.get("raw", data),
        "module": normalized.get("module", "unknown"),
    }

    if event["traceId"] == "missing":
        return None, "missing_trace_id"

    return event, None


def classify_result(result: Dict, stale_flush: bool) -> Dict:
    status = "ok"
    if stale_flush:
        status = "timeout"
    elif result.get("missing"):
        status = "error"
    result["status"] = status
    return result


class TraceAggregator:
    def __init__(self, idle_flush_sec: int = 30) -> None:
        self.idle_flush_sec = idle_flush_sec
        self.traces: Dict[str, TraceBuffer] = {}

    def ingest(self, ev: Dict) -> List[Dict]:
        tid = ev.get("traceId", "missing")
        if tid == "missing":
            return []

        buf = self.traces.setdefault(tid, TraceBuffer(trace_id=tid))
        buf.add(ev)
        dlog(f"traceId={tid} event={ev['name']} aggregated_events={len(buf.events)} open_traces={len(self.traces)}")

        if buf.ready():
            result = analyze({"traceId": tid, "events": buf.events})
            self.traces.pop(tid, None)
            return [classify_result(result, stale_flush=False)]

        return []

    def flush_stale(self) -> List[Dict]:
        now = time.time()
        stale = [tid for tid, b in self.traces.items() if now - b.last_update >= self.idle_flush_sec]
        results: List[Dict] = []
        for tid in stale:
            buf = self.traces.pop(tid)
            result = analyze({"traceId": tid, "events": buf.events})
            results.append(classify_result(result, stale_flush=True))
            dlog(f"traceId={tid} stale_flush timeout open_traces={len(self.traces)}")
        return results


def tail_events(log_path: str, from_beginning: bool = False, poll_interval: float = 0.5) -> Generator[Dict, None, None]:
    fp = None
    inode = None
    offset_to_end = not from_beginning
    read_count = 0

    while True:
        path = Path(log_path)
        if not path.exists():
            dlog(f"waiting_log_file path={log_path}")
            time.sleep(poll_interval)
            continue

        stat = path.stat()
        if fp is None or inode != stat.st_ino:
            if fp is not None:
                fp.close()
            fp = open(log_path, "r", encoding="utf-8")
            inode = stat.st_ino
            dlog(f"opened_log_file path={log_path} inode={inode}")
            if offset_to_end:
                fp.seek(0, os.SEEK_END)
                offset_to_end = False
                dlog("seek_to_end_for_tail_mode")

        line = fp.readline()
        if not line:
            time.sleep(poll_interval)
            continue

        read_count += 1
        dlog(f"line_read_count={read_count} bytes={len(line)}")
        ev, reason = parse_line(line)
        if ev is None:
            dlog(f"line_skipped reason={reason}")
            continue

        dlog(f"line_parsed_ok event={ev['name']} traceId={ev['traceId']} module={ev['module']}")
        yield ev


def process_file(
    log_path: str,
    idle_flush_sec: int = 30,
    poll_interval: float = 0.5,
    from_beginning: bool = False,
    on_result: Optional[AnalyzeCallback] = None,
) -> None:
    aggregator = TraceAggregator(idle_flush_sec=idle_flush_sec)
    print(f"[reader] tailing: {log_path} (from_beginning={from_beginning})", flush=True)

    for ev in tail_events(log_path, from_beginning=from_beginning, poll_interval=poll_interval):
        for result in aggregator.ingest(ev):
            if on_result:
                on_result(result)
            else:
                print("\n[reader] trace complete", flush=True)
                print_report(result)

        for result in aggregator.flush_stale():
            if on_result:
                on_result(result)
            else:
                print("\n[reader] idle flush", flush=True)
                print_report(result)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Tail OpenClaw JSONL logs and analyze traces")
    parser.add_argument("log_file", nargs="?", default="logs/openclaw-runtime.jsonl", help="Path to JSONL log file")
    parser.add_argument("--idle-flush-sec", type=int, default=30, help="Flush inactive trace buffers")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="File tail poll interval")
    parser.add_argument("--from-beginning", action="store_true", help="Read existing log lines from file start")
    args = parser.parse_args()

    process_file(
        args.log_file,
        idle_flush_sec=args.idle_flush_sec,
        poll_interval=args.poll_interval,
        from_beginning=args.from_beginning,
    )


if __name__ == "__main__":
    main()
