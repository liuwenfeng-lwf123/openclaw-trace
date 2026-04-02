#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REQUIRED_HINTS = [
    'dashboard.send.click',
    'gateway.message.received',
    'provider.first_token',
    'dashboard.render.done',
]

SEARCH_ROOTS = [Path('/var/log'), Path('/workspace'), Path('/tmp')]
EXCLUDE = {'sample_stream.jsonl', 'sample_trace.json'}


def looks_real(path: Path) -> bool:
    if path.name in EXCLUDE:
        return False
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return False
    if not text.strip():
        return False
    return sum(1 for h in REQUIRED_HINTS if h in text) >= 2


def main() -> None:
    candidates = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob('*.jsonl'):
            if looks_real(p):
                candidates.append(p)

    if not candidates:
        print('NOT_FOUND')
        return

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(str(candidates[0]))


if __name__ == '__main__':
    main()
