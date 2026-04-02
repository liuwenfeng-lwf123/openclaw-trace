#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def emit_jsonl_event(log_file: str, trace_id: str, event: str, module: str, ts: Optional[str] = None) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'ts': ts or now_iso(),
        'traceId': trace_id,
        'event': event,
        'module': module,
    }
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(payload, ensure_ascii=False) + '\n')
