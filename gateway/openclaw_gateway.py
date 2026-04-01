#!/usr/bin/env python3
"""OpenClaw Gateway 最小埋点实现（MVP）"""

from __future__ import annotations

import time
from typing import Iterable

from src.openclaw_jsonl_logger import emit_jsonl_event


class OpenClawGateway:
    def __init__(self, log_file: str = 'logs/openclaw-runtime.jsonl') -> None:
        self.log_file = log_file

    def handle_message(self, trace_id: str, provider_tokens: Iterable[str]) -> str:
        # T2 = gateway.message.received
        emit_jsonl_event(self.log_file, trace_id, 'gateway.message.received', 'gateway')

        # T3 = gateway.processing.start
        emit_jsonl_event(self.log_file, trace_id, 'gateway.processing.start', 'gateway')

        # T4 = provider.request.start
        emit_jsonl_event(self.log_file, trace_id, 'provider.request.start', 'gateway')

        output = []
        first_token_emitted = False
        for token in provider_tokens:
            time.sleep(0.01)
            if not first_token_emitted:
                # T5 = provider.first_token
                emit_jsonl_event(self.log_file, trace_id, 'provider.first_token', 'gateway')
                first_token_emitted = True
            output.append(token)

        # T6 = provider.response.complete
        emit_jsonl_event(self.log_file, trace_id, 'provider.response.complete', 'gateway')
        return ''.join(output)
