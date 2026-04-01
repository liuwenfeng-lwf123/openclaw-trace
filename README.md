# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析。

## 本地桌面版（MVP）

已实现一个本地桌面窗口软件（Tkinter），复用现有 `trace_analyzer.py` 和 `realtime_log_reader.py`。

### 桌面版能力
- 桌面窗口实时刷新。
- 左侧显示最近消息（trace）列表。
- 点击某条消息查看完整链路分段。
- 显示每段耗时（含 `missing`）。
- 最慢环节红色高亮。
- 显示最慢环节占比和原因提示。

### 文件路径
- `src/desktop_app.py`：桌面应用入口与 UI。
- `src/realtime_log_reader.py`：实时日志读取与 trace 聚合（支持回调给桌面 UI）。
- `src/trace_analyzer.py`：链路时延分析核心。
- `src/simulate_openclaw_runtime.py`：生成一条完整运行日志。

### 启动方式

```bash
# 1) 生成模拟日志（可选）
: > logs/openclaw-runtime.jsonl
python3 src/simulate_openclaw_runtime.py

# 2) 启动桌面软件（默认会先读取已有日志，再实时刷新）
python3 src/desktop_app.py --log-file logs/openclaw-runtime.jsonl
```

仅监听新增日志：

```bash
python3 src/desktop_app.py --log-file logs/openclaw-runtime.jsonl --tail
```

## JSONL 日志格式

统一格式：

```json
{
  "ts": "2026-04-01T10:00:00.123Z",
  "traceId": "trace-xxx",
  "event": "provider.first_token",
  "module": "gateway"
}
```

## 现有埋点（MVP）
- Gateway (`gateway/openclaw_gateway.py`)：
  - `gateway.message.received` (T2)
  - `gateway.processing.start` (T3)
  - `provider.request.start` (T4)
  - `provider.first_token` (T5)
  - `provider.response.complete` (T6)
- Dashboard (`dashboard/src/traceInstrumentation.ts`)：
  - `dashboard.send.click` (T0)
  - `dashboard.request.sent` (T1)
  - `dashboard.push.start` (T7)
  - `dashboard.render.done` (T8)
