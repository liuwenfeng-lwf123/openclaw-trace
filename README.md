# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析。

## 实时可视化（React Flow + WebSocket）

已废弃 Tkinter UI，当前采用：
- Python 分析层（保留并复用）
- Python WebSocket 桥接层
- React + React Flow 链路图前端

### 目录结构
- `src/trace_analyzer.py`：链路分析核心（复用）。
- `src/realtime_log_reader.py`：实时日志读取与按 traceId 聚合（复用/增强）。
- `backend/ws_bridge.py`：读取 OpenClaw 运行日志并通过 WebSocket 推送分析结果。
- `web/`：React Flow 前端可视化。

### 前端能力
- 最近消息列表
- 单条消息完整链路图（调用链样式）
- 每段耗时标签
- 最慢环节红色高亮
- 最慢环节占比
- 原因提示
- WebSocket 实时自动刷新

### 真实事件流接入
OpenClaw 运行时日志（JSONL） -> `src/realtime_log_reader.py` -> `backend/ws_bridge.py` -> WebSocket -> React Flow 前端。

日志格式：

```json
{
  "ts": "2026-04-01T10:00:00.123Z",
  "traceId": "trace-xxx",
  "event": "provider.first_token",
  "module": "gateway"
}
```

### 本地最小可运行

1) 启动桥接层（监听真实运行日志）

```bash
python3 backend/ws_bridge.py --log-file logs/openclaw-runtime.jsonl
```

2) 启动前端

```bash
cd web
npm install
npm run dev
```

3) 模拟写入一条真实链路日志（可选）

```bash
python3 src/simulate_openclaw_runtime.py
```

打开 Vite 输出地址（通常 `http://127.0.0.1:5173`）即可实时看到更新。
