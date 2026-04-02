#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from realtime_log_reader import process_file  # noqa: E402

DEBUG = os.getenv("OPENCLAW_TRACE_DEBUG", "1") == "1"


def wlog(msg: str) -> None:
    if DEBUG:
        print(f"[ws-debug] {msg}", flush=True)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


class WsBridge:
    def __init__(self, log_file: str, from_beginning: bool) -> None:
        self.log_file = log_file
        self.from_beginning = from_beginning
        self.clients: Set[Any] = set()
        self.queue: "asyncio.Queue[Dict]" = asyncio.Queue()
        self.latest_results: List[Dict] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    def on_analyze_result(self, result: Dict) -> None:
        payload = to_jsonable(result)
        self.latest_results.insert(0, payload)
        if len(self.latest_results) > 100:
            self.latest_results.pop()

        wlog(f"received_from_reader traceId={payload.get('traceId')} status={payload.get('status')} cached={len(self.latest_results)}")

        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    async def consumer_loop(self) -> None:
        while True:
            payload = await self.queue.get()
            if not self.clients:
                wlog("no_clients_skip_broadcast")
                continue

            msg = json.dumps({"type": "trace_update", "data": payload, "meta": {"logFile": self.log_file}}, ensure_ascii=False)
            wlog(f"broadcast_prepare clients={len(self.clients)} traceId={payload.get('traceId')}")
            dead = []
            for ws in self.clients:
                try:
                    await ws.send(msg)
                except Exception as e:
                    wlog(f"broadcast_failed err={e}")
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
            wlog(f"broadcast_sent clients={len(self.clients)} traceId={payload.get('traceId')}")

    async def handler(self, websocket: Any) -> None:
        import websockets

        self.clients.add(websocket)
        wlog(f"client_connected total={len(self.clients)}")
        snapshot = json.dumps({"type": "snapshot", "data": self.latest_results, "meta": {"logFile": self.log_file}}, ensure_ascii=False)
        await websocket.send(snapshot)
        try:
            async for _ in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            wlog("client_connection_closed")
        finally:
            self.clients.discard(websocket)
            wlog(f"client_disconnected total={len(self.clients)}")

    async def run(self, host: str, port: int) -> None:
        import websockets

        if "*" not in self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.log_file).touch(exist_ok=True)
        else:
            wlog(f"glob_log_path_detected skip_touch path={self.log_file}")

        self.loop = asyncio.get_running_loop()
        self.loop.run_in_executor(
            None,
            lambda: process_file(
                log_path=self.log_file,
                idle_flush_sec=2,
                poll_interval=0.3,
                from_beginning=self.from_beginning,
                on_result=self.on_analyze_result,
            ),
        )

        asyncio.create_task(self.consumer_loop())

        async with websockets.serve(self.handler, host, port):
            print(f"[ws-bridge] listening host={host} port={port} log={self.log_file}")
            wlog("websocket_server_started")
            await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw realtime WebSocket bridge")
    parser.add_argument("--log-file", default="/tmp/openclaw/openclaw-*.log")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tail", action="store_true", help="Only stream new lines")
    args = parser.parse_args()

    bridge = WsBridge(log_file=args.log_file, from_beginning=not args.tail)
    asyncio.run(bridge.run(args.host, args.port))


if __name__ == "__main__":
    main()
