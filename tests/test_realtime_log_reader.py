from __future__ import annotations

import queue
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.realtime_log_reader import _select_log_target, tail_events


def _next_async(gen):
    q: "queue.Queue[object]" = queue.Queue()

    def run():
        try:
            q.put(next(gen))
        except Exception as exc:  # pragma: no cover
            q.put(exc)

    threading.Thread(target=run, daemon=True).start()
    return q


class TestRealtimeLogReader(unittest.TestCase):
    def test_select_log_target_falls_back_to_newest_log(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            older = base / "openclaw-2026-04-01.log"
            newer = base / "runtime.log"
            older.write_text("x", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("y", encoding="utf-8")

            selected = _select_log_target(str(base / "trace-*.log"), None)
            self.assertEqual(selected, newer)

            selected_missing = _select_log_target(str(base / "openclaw-2099-01-01.log"), None)
            self.assertEqual(selected_missing, newer)

    def test_tail_events_handles_truncate_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "openclaw-2026-04-02.log"
            log_path.write_text("", encoding="utf-8")

            gen = tail_events(str(log_path), from_beginning=False, poll_interval=0.02)
            try:
                first = {
                    "event": "dashboard.send.click",
                    "traceId": "t-1",
                    "ts": "2026-04-02T00:00:00Z",
                    "padding": "x" * 200,
                }
                q1 = _next_async(gen)
                time.sleep(0.05)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(first, ensure_ascii=False) + "\n")
                    f.flush()
                ev1 = q1.get(timeout=2.0)
                if isinstance(ev1, Exception):  # pragma: no cover
                    raise ev1
                self.assertEqual(ev1["traceId"], "t-1")

                # truncate then append a new line with same inode
                q2 = _next_async(gen)
                time.sleep(0.05)
                with log_path.open("w", encoding="utf-8") as f:
                    second = {
                        "event": "dashboard.request.sent",
                        "traceId": "t-1",
                        "ts": "2026-04-02T00:00:01Z",
                    }
                    f.write(json.dumps(second, ensure_ascii=False) + "\n")
                    f.flush()

                ev2 = q2.get(timeout=2.0)
                if isinstance(ev2, Exception):  # pragma: no cover
                    raise ev2
                self.assertEqual(ev2["name"], "dashboard.request.sent")
            finally:
                gen.close()


if __name__ == "__main__":
    unittest.main()
