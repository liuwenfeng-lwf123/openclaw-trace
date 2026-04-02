#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import glob
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
VERBOSE = os.getenv("OPENCLAW_TRACE_DEBUG_VERBOSE", "0") == "1"


def dlog(msg: str) -> None:
    if DEBUG:
        print(f"[reader-debug] {msg}", flush=True)


@dataclass
class TraceBuffer:
    trace_id: str
    key_type: str
    events: List[Dict] = field(default_factory=list)
    seen: set = field(default_factory=set)
    event_timeline: List[Dict] = field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    last_error: Optional[str] = None
    last_update: float = field(default_factory=time.time)
    last_emit: float = field(default_factory=lambda: 0.0)

    def add(self, ev: Dict) -> None:
        self.events.append({"name": ev["name"], "timestamp": ev["timestamp"]})
        self.seen.add(ev["name"])
        self.event_timeline.append({
            "ts": ev["timestamp"],
            "event": ev["name"],
            "module": ev.get("module", "unknown"),
            "provider": ev.get("provider"),
            "model": ev.get("model"),
            "error": ev.get("error"),
        })
        if ev.get("provider"):
            self.provider = ev["provider"]
        if ev.get("model"):
            self.model = ev["model"]
        if ev.get("error"):
            self.last_error = str(ev["error"])
        self.last_update = time.time()

    def ready(self) -> bool:
        # 既支持标准 T8 完整链路，也支持真实 run 结束事件
        return (
            "dashboard.render.done" in self.seen
            or "embedded_run_agent_end" in self.seen
            or all(e in self.seen for e in REQUIRED_EVENTS)
        )


def parse_line(line: str) -> Tuple[Optional[Dict], Optional[str]]:
    raw_line = line.strip()
    if not raw_line:
        return None, "empty_line"

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
        "groupKeyType": normalized.get("groupKeyType", "unknown"),
        "raw": normalized.get("raw", data),
        "module": normalized.get("module", "unknown"),
        "provider": normalized.get("provider"),
        "model": normalized.get("model"),
        "error": normalized.get("error"),
        "tags": normalized.get("tags"),
    }

    if event["traceId"] == "missing":
        return None, "missing_trace_id"

    return event, None


def classify_status(result: Dict, stale_flush: bool, buffer: TraceBuffer) -> Tuple[str, Optional[str]]:
    if stale_flush:
        return "timeout", buffer.last_error or "stale_flush_timeout"

    text = " ".join([e["event"].lower() for e in buffer.event_timeline])
    if any(k in text for k in ["timeout", "rate limit", "http 401", "econnrefused", "recall failed"]):
        return "error", buffer.last_error or "runtime_error_event"

    if result.get("missing"):
        return "error", buffer.last_error or "missing_required_stage"

    return "ok", buffer.last_error


def enrich_result(result: Dict, stale_flush: bool, buffer: TraceBuffer, partial: bool = False) -> Dict:
    status, reason = classify_status(result, stale_flush, buffer)
    if partial and not stale_flush:
        status = "partial"
    result["status"] = status
    result["error_reason"] = reason
    result["group_key_type"] = buffer.key_type
    result["provider"] = buffer.provider
    result["model"] = buffer.model
    result["event_timeline"] = buffer.event_timeline
    result["partial"] = partial
    return result


class TraceAggregator:
    def __init__(self, idle_flush_sec: int = 30) -> None:
        self.idle_flush_sec = idle_flush_sec
        self.traces: Dict[str, TraceBuffer] = {}

    def ingest(self, ev: Dict) -> List[Dict]:
        tid = ev.get("traceId", "missing")
        if tid == "missing":
            return []

        buf = self.traces.get(tid)
        if not buf:
            buf = TraceBuffer(trace_id=tid, key_type=ev.get("groupKeyType", "unknown"))
            self.traces[tid] = buf
        buf.add(ev)

        dlog(
            f"accepted_event event={ev['name']} key_type={buf.key_type} key={tid} "
            f"aggregated_events={len(buf.events)} open_traces={len(self.traces)}"
        )

        now = time.time()
        if buf.ready():
            result = analyze({"traceId": tid, "events": buf.events})
            self.traces.pop(tid, None)
            return [enrich_result(result, stale_flush=False, buffer=buf, partial=False)]

        # 即使未完成也周期性推送部分链路，确保前端“有反应”
        if now - buf.last_emit >= 1.0:
            buf.last_emit = now
            partial = analyze({"traceId": tid, "events": buf.events})
            return [enrich_result(partial, stale_flush=False, buffer=buf, partial=True)]

        return []

    def flush_stale(self) -> List[Dict]:
        now = time.time()
        stale = [tid for tid, b in self.traces.items() if now - b.last_update >= self.idle_flush_sec]
        results: List[Dict] = []
        for tid in stale:
            buf = self.traces.pop(tid)
            result = analyze({"traceId": tid, "events": buf.events})
            results.append(enrich_result(result, stale_flush=True, buffer=buf, partial=False))
            dlog(f"stale_flush key_type={buf.key_type} key={tid} open_traces={len(self.traces)}")
        return results


def _select_log_target(config_path: str, current: Optional[Path]) -> Optional[Path]:
    def newest_in_dir(base_dir: Path) -> Optional[Path]:
        candidates: List[Path] = []
        candidates.extend(base_dir.glob("openclaw-*.log"))
        candidates.extend(base_dir.glob("*.log"))
        uniq = {p.resolve(): p for p in candidates if p.is_file()}
        ordered = sorted(uniq.values(), key=lambda x: x.stat().st_mtime, reverse=True)
        return ordered[0] if ordered else None

    # explicit glob support
    if "*" in config_path:
        matches = sorted([Path(x) for x in glob.glob(config_path)], key=lambda x: x.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
        # fallback to broader *.log discovery in same folder
        return newest_in_dir(Path(config_path).parent)

    p = Path(config_path)
    if p.exists():
        # if sibling daily file newer, switch to newer file
        sibling_newest = newest_in_dir(p.parent)
        if sibling_newest and sibling_newest.stat().st_mtime > p.stat().st_mtime:
            return sibling_newest
        return p

    # fallback: try newest openclaw daily log in same dir
    return newest_in_dir(p.parent)


def tail_events(log_path: str, from_beginning: bool = False, poll_interval: float = 0.5) -> Generator[Dict, None, None]:
    fp = None
    inode = None
    offset_to_end = not from_beginning
    read_count = 0
    skip_stats: Dict[str, int] = {}
    target_path: Optional[Path] = None
    last_idle_log = 0.0
    last_size = 0

    try:
        while True:
            selected = _select_log_target(log_path, target_path)
            if selected is None:
                dlog(f"waiting_log_file path={log_path}")
                time.sleep(poll_interval)
                continue

            if target_path is None or selected != target_path:
                dlog(f"log_target_switched old={target_path} new={selected}")
                target_path = selected
                inode = None
                last_size = 0

            stat = target_path.stat()
            if fp is None or inode != stat.st_ino:
                if fp is not None:
                    fp.close()
                fp = open(target_path, "r", encoding="utf-8")
                inode = stat.st_ino
                last_size = stat.st_size
                dlog(f"opened_log_file path={target_path} inode={inode}")
                if offset_to_end:
                    fp.seek(0, os.SEEK_END)
                    offset_to_end = False
                    dlog("seek_to_end_for_tail_mode")
            elif stat.st_size < last_size or fp.tell() > stat.st_size:
                # handle truncate-in-place rotation (inode unchanged, file shrinks)
                dlog(f"log_file_truncated path={target_path} old_offset={fp.tell()} new_size={stat.st_size} -> seek_start")
                fp.seek(0)
            last_size = stat.st_size

            line = fp.readline()
            if not line:
                now = time.time()
                if now - last_idle_log > 5:
                    dlog(f"tail_idle waiting_new_line file={target_path}")
                    last_idle_log = now
                time.sleep(poll_interval)
                continue

            read_count += 1
            if VERBOSE or read_count % 200 == 0:
                dlog(f"line_read_count={read_count} bytes={len(line)} file={target_path.name}")
            ev, reason = parse_line(line)
            if ev is None:
                skip_stats[reason or "unknown"] = skip_stats.get(reason or "unknown", 0) + 1
                if VERBOSE or read_count % 200 == 0:
                    dlog(f"line_skipped reason={reason} skip_stats={skip_stats}")
                continue

            dlog(
                f"line_parsed_ok event={ev['name']} key_type={ev['groupKeyType']} "
                f"key={ev['traceId']} module={ev['module']}"
            )
            yield ev
    finally:
        if fp is not None:
            fp.close()


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
