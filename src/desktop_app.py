#!/usr/bin/env python3
"""OpenClaw 桌面链路监控软件（MVP, Tkinter）"""

from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Dict, List

from realtime_log_reader import process_file


class OpenClawDesktopApp(tk.Tk):
    def __init__(self, log_file: str, from_beginning: bool = True) -> None:
        super().__init__()
        self.title("OpenClaw Link Trace Monitor")
        self.geometry("1100x680")

        self.log_file = log_file
        self.from_beginning = from_beginning
        self.result_queue: "queue.Queue[Dict]" = queue.Queue()
        self.recent_results: List[Dict] = []
        self.max_recent = 200

        self._build_ui()
        self._start_reader_thread()
        self.after(300, self._drain_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(root, text="最近消息")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.trace_list = tk.Listbox(left)
        self.trace_list.grid(row=0, column=0, sticky="nsew")
        self.trace_list.bind("<<ListboxSelect>>", self._on_trace_select)

        right = ttk.LabelFrame(root, text="链路详情")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        self.trace_id_var = tk.StringVar(value="traceId: -")
        self.slowest_var = tk.StringVar(value="最慢环节: -")
        self.hint_var = tk.StringVar(value="原因提示: -")

        ttk.Label(right, textvariable=self.trace_id_var).grid(row=0, column=0, sticky="w", pady=(4, 4))
        ttk.Label(right, textvariable=self.slowest_var).grid(row=1, column=0, sticky="w", pady=(0, 6))

        cols = ("segment", "label", "duration")
        self.segment_tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        self.segment_tree.heading("segment", text="阶段")
        self.segment_tree.heading("label", text="含义")
        self.segment_tree.heading("duration", text="耗时")
        self.segment_tree.column("segment", width=100, anchor="center")
        self.segment_tree.column("label", width=280)
        self.segment_tree.column("duration", width=140, anchor="center")
        self.segment_tree.grid(row=2, column=0, sticky="nsew")

        self.segment_tree.tag_configure("slowest", foreground="red")

        ttk.Label(right, textvariable=self.hint_var, wraplength=620).grid(row=3, column=0, sticky="w", pady=(8, 4))

    def _start_reader_thread(self) -> None:
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_file).touch(exist_ok=True)

        def on_result(result: Dict) -> None:
            self.result_queue.put(result)

        thread = threading.Thread(
            target=process_file,
            kwargs={
                "log_path": self.log_file,
                "idle_flush_sec": 2,
                "poll_interval": 0.3,
                "from_beginning": self.from_beginning,
                "on_result": on_result,
            },
            daemon=True,
        )
        thread.start()

    def _drain_queue(self) -> None:
        updated = False
        while True:
            try:
                result = self.result_queue.get_nowait()
            except queue.Empty:
                break
            self.recent_results.insert(0, result)
            if len(self.recent_results) > self.max_recent:
                self.recent_results.pop()
            updated = True

        if updated:
            self._refresh_trace_list()

        self.after(300, self._drain_queue)

    def _refresh_trace_list(self) -> None:
        cur = self.trace_list.curselection()
        self.trace_list.delete(0, tk.END)
        for idx, res in enumerate(self.recent_results):
            total = next((s.ms for s in res["segments"] if s.key == "T8-T0"), None)
            total_text = "missing" if total is None else f"{total:.2f}ms"
            self.trace_list.insert(idx, f"{res['traceId']} | total={total_text}")

        if self.recent_results:
            if cur:
                select_idx = min(cur[0], len(self.recent_results) - 1)
            else:
                select_idx = 0
            self.trace_list.selection_clear(0, tk.END)
            self.trace_list.selection_set(select_idx)
            self._render_detail(self.recent_results[select_idx])

    def _on_trace_select(self, _: tk.Event) -> None:
        if not self.trace_list.curselection():
            return
        idx = self.trace_list.curselection()[0]
        if idx < len(self.recent_results):
            self._render_detail(self.recent_results[idx])

    def _render_detail(self, result: Dict) -> None:
        self.trace_id_var.set(f"traceId: {result['traceId']}")

        for item in self.segment_tree.get_children():
            self.segment_tree.delete(item)

        slowest = result.get("slowest")
        slowest_key = slowest["key"] if slowest else None

        for seg in result["segments"]:
            dur = "missing" if seg.ms is None else f"{seg.ms:.2f} ms"
            tag = ("slowest",) if seg.key == slowest_key else ()
            self.segment_tree.insert("", tk.END, values=(seg.key, seg.label, dur), tags=tag)

        if slowest:
            ratio = slowest.get("ratio_pct")
            ratio_text = "missing" if ratio is None else f"{ratio:.2f}%"
            self.slowest_var.set(
                f"最慢环节: {slowest['key']} | 耗时: {slowest['ms']:.2f} ms | 占比: {ratio_text}"
            )
            self.hint_var.set(f"原因提示: {slowest.get('hint', '-')}")
        else:
            self.slowest_var.set("最慢环节: missing")
            self.hint_var.set("原因提示: missing")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw Desktop Trace Monitor")
    parser.add_argument("--log-file", default="logs/openclaw-runtime.jsonl", help="OpenClaw runtime JSONL log")
    parser.add_argument("--tail", action="store_true", help="Only read new lines (do not replay existing logs)")
    args = parser.parse_args()

    app = OpenClawDesktopApp(log_file=args.log_file, from_beginning=not args.tail)
    app.mainloop()


if __name__ == "__main__":
    main()
