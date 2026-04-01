# openclaw-trace

## 代码改造目标（仓库侧）
本仓库只负责：
1) 适配真实 OpenClaw 日志为标准 JSONL 事件流；
2) 实时聚合 + 分析 + WebSocket 推送；
3) React Flow 实时可视化。

## 关键文件与作用

- `src/openclaw_event_adapter.py`
  - 将真实 OpenClaw 日志结构适配为标准事件：`{ts, traceId, event, module}`。
  - 支持字段别名：`timestamp/time/@timestamp`、`trace_id/x-trace-id/headers.x-trace-id`、`event/name/stage`。

- `src/realtime_log_reader.py`
  - 实时 tail 指定日志文件（支持文件重建/轮转）。
  - 按 `traceId` 聚合事件并调用 `trace_analyzer.py`。

- `backend/ws_bridge.py`
  - 启动 WebSocket 服务。
  - 将 reader 结果实时推送为 `snapshot` / `trace_update`。
  - 额外携带 `meta.logFile`，前端显示当前接入的是哪条日志路径。

- `web/src/App.jsx`
  - 连接 WebSocket，自动重连。
  - 显示最近消息列表、链路图、每段耗时、最慢红色高亮、占比、原因提示。
  - 显示连接状态和 source log file（便于本机验收）。

## 你本机需要提供的内容

请至少提供其中一项：

1. **真实日志路径**（推荐）
   - 例如：`/tmp/openclaw/runtime.jsonl` 或 `/var/log/openclaw/runtime.jsonl`

2. **真实日志样本文件（脱敏）**
   - 至少 20 行 JSONL
   - 必须包含：`ts/timestamp`、`traceId(或别名)`、`event(或别名)`

## 本机最终验证命令（真实接入）

### 0) 安装依赖
```bash
pip install -r requirements.txt
cd web && npm install && cd ..
```

### 1) 启动后端（把 REAL_LOG_PATH 替换成你本机真实路径）
```bash
REAL_LOG_PATH=/your/real/openclaw-runtime.jsonl
python3 backend/ws_bridge.py --log-file "$REAL_LOG_PATH" --tail
```

启动成功关键输出：
```text
[reader] tailing: <REAL_LOG_PATH> (from_beginning=False)
[ws-bridge] ws://127.0.0.1:8765 -> <REAL_LOG_PATH>
```

### 2) 启动前端
```bash
cd web
npm run dev
```

### 3) 打开页面后，执行实时验收
- 在真实 OpenClaw 发一条消息；
- 页面左侧“最近消息”新增 traceId；
- 顶部 `source:` 显示与你启动 bridge 时一致的 `REAL_LOG_PATH`；
- 主图最慢链路红色高亮。

### 4) 证明 traceId 与真实日志记录一致
```bash
TRACE_ID=<页面左侧新出现的traceId>
REAL_LOG_PATH=/your/real/openclaw-runtime.jsonl
rg "$TRACE_ID" "$REAL_LOG_PATH" | head -n 5
```

看到日志命中即为“页面 traceId ↔ 真实日志记录”对齐成功。
