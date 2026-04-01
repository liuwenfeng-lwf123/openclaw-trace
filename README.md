# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析。

## 实时可视化（React Flow + WebSocket）

已废弃 Tkinter UI，当前采用：
- Python 分析层（复用 `trace_analyzer.py`）
- Python 日志监听层（复用 `realtime_log_reader.py`）
- Python WebSocket 桥接层（`backend/ws_bridge.py`）
- React Flow 前端（`web/`）

## 关键问题结论

1) 前端数据来源：
- **来自 `backend/ws_bridge.py` 实时推送的运行日志分析结果**，不是前端直接读 sample 文件。
- 是否真实，取决于 `--log-file` 指向的文件是否为真实 OpenClaw 运行日志。

2) 自动刷新：
- 真实 OpenClaw 新增日志行后，Reader 会实时 tail，Bridge 立刻推送到 WebSocket，前端 `onmessage` 后马上刷新。

## T0~T8 打点位置（当前最小版）

### Gateway（Python）
文件：`gateway/openclaw_gateway.py`
- T2 `gateway.message.received`
- T3 `gateway.processing.start`
- T4 `provider.request.start`
- T5 `provider.first_token`
- T6 `provider.response.complete`

### Dashboard（前端）
文件：`dashboard/src/traceInstrumentation.ts`
- T0 `dashboard.send.click`
- T1 `dashboard.request.sent`
- T7 `dashboard.push.start`
- T8 `dashboard.render.done`

### missing 判定
文件：`src/trace_analyzer.py`
- 某段起止任一时间点不存在 => `calc_ms` 返回 `None` => 页面显示 `missing`。

### 最慢环节计算
文件：`src/trace_analyzer.py`
- 在分段里排除聚合段 `T5-T0`、`T8-T0`，从其余有效段里取最大耗时。
- 占比 = `slowest.ms / (T8-T0)`。

## 真实事件流链路

OpenClaw Runtime JSONL -> `src/realtime_log_reader.py` -> `backend/ws_bridge.py` -> WebSocket -> `web/src/App.jsx`

## 最小可运行步骤（真实时）

### 0. 准备依赖

```bash
pip install -r requirements.txt
cd web && npm install
```

### 1. 启动后端桥接（指向真实 OpenClaw 日志）

```bash
python3 backend/ws_bridge.py --log-file /path/to/real/openclaw-runtime.jsonl --tail
```

> `--tail` 表示只监听启动后的新增日志（真实线上建议开启）。

### 2. 启动前端

```bash
cd web
npm run dev
```

### 3. 在真实 OpenClaw 发一条消息

要求 OpenClaw 在运行日志里写 JSONL 事件，字段至少包含：

```json
{"ts":"...","traceId":"...","event":"dashboard.send.click","module":"dashboard"}
```

### 4. 验证实时刷新成功

- 浏览器打开 Vite 地址（默认 `http://127.0.0.1:5173`）。
- 发送真实消息后：
  - 左侧“最近消息”出现新的 traceId；
  - 主画布出现完整 T0~T8 链路；
  - 最慢环节红色高亮；
  - 顶部显示最慢占比和原因提示。

## JSONL 格式

```json
{
  "ts": "2026-04-01T10:00:00.123Z",
  "traceId": "trace-xxx",
  "event": "provider.first_token",
  "module": "gateway"
}
```
