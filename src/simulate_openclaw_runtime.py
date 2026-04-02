#!/usr/bin/env python3
"""生成一条完整 OpenClaw 运行日志（含前端+网关 9 个事件）"""

from __future__ import annotations

import uuid
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gateway.openclaw_gateway import OpenClawGateway
from src.openclaw_jsonl_logger import emit_jsonl_event


def simulate(log_file: str = 'logs/openclaw-runtime.jsonl') -> str:
    trace_id = str(uuid.uuid4())

    # Dashboard: T0 / T1
    emit_jsonl_event(log_file, trace_id, 'dashboard.send.click', 'dashboard')
    emit_jsonl_event(log_file, trace_id, 'dashboard.request.sent', 'dashboard')

    # Gateway + Provider: T2~T6
    gateway = OpenClawGateway(log_file=log_file)
    gateway.handle_message(trace_id, provider_tokens=['你', '好', '，', '世', '界'])

    # Dashboard: T7 / T8
    emit_jsonl_event(log_file, trace_id, 'dashboard.push.start', 'dashboard')
    emit_jsonl_event(log_file, trace_id, 'dashboard.render.done', 'dashboard')

    return trace_id


if __name__ == '__main__':
    tid = simulate()
    print(f'simulated traceId={tid}')
