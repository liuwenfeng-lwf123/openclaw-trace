# OpenClaw Web 实时监控（验收优先）

## 当前验收目标
只修这一条链路：
真实 OpenClaw 日志新增 -> reader 解析聚合 -> ws 广播 -> 前端实时新增记录。

## 改动文件与作用

- `src/openclaw_event_adapter.py`
  - 适配真实日志形态（包括 `{"0":"...","1":"...","_meta":{...},"time":"..."}`）
  - 明确提取：event / traceId / ts / module
  - traceId 缺失时尝试 `_meta.request_id/message_id/conversation_id` 生成 `derived-*`

- `src/realtime_log_reader.py`
  - 增加逐层调试输出：开文件、读到行数、解析成功/失败、跳过原因、traceId 提取结果、聚合数量
  - 解析失败/无 traceId 行会跳过并打印 reason
  - 输出结果附带 `status=ok|error|timeout`

- `backend/ws_bridge.py`
  - 增加调试输出：服务启动、收到 reader 数据、广播准备数量、广播成功/失败
  - ws payload 带 `meta.logFile`

- `web/src/App.jsx`
  - 增加调试输出：ws connect/open/close/error、payload、state 更新
  - 自动选中最新 trace
  - 列表和详情显示 `status`，缺失阶段标记 `missing`，timeout/error 高亮

## 真实日志字段规则（当前实现）

1. 事件识别字段：
- 优先：`event | name | stage | _meta.event | _meta.event_name`
- 否则从字符串内容推断（如 `provider.first_token`、`response complete`）

2. traceId 提取：
- 优先：`traceId | trace_id | x_trace_id | x-trace-id | _meta.traceId | _meta.trace_id | headers.x-trace-id`

3. 无直接 traceId 时：
- 使用 `_meta.request_id/message_id/conversation_id` 生成 `derived-<md5前16位>`
- 若仍无可关联信息，返回 `missing` 并跳过该行

4. 会跳过的行：
- 非 JSON
- JSON 不是对象
- 无法识别事件
- traceId 缺失且无法推导

5. 跳过原因（reader debug）：
- `invalid_json | not_dict | adapter_no_event | missing_trace_id | empty_line`

## 本机验证命令（真实路径）

真实路径：`/tmp/openclaw/openclaw-$(date +%F).log`

### 1) 启动后端（开启 debug）
```bash
export OPENCLAW_TRACE_DEBUG=1
LOG_FILE="/tmp/openclaw/openclaw-$(date +%F).log"
python3 backend/ws_bridge.py --log-file "$LOG_FILE" --tail
```

期望看到：
- `[reader] tailing: ...`
- `[ws-bridge] ws://127.0.0.1:8765 -> ...`
- `[ws-debug] websocket_server_started`

### 2) 启动前端
```bash
cd web
npm install
npm run dev
```

浏览器 Console 期望看到：
- `[ui-ws] connected`
- `[ui-ws] payload ...`
- `[ui-state] trace_update ...`

### 3) 在真实 OpenClaw 发一条消息后验证
- 左侧新增 traceId
- 自动选中新 trace
- 右侧详情刷新
- 最慢边红色高亮
- missing / timeout / error 状态可见

### 4) traceId 与真实日志对齐
```bash
TRACE_ID=<页面新出现的traceId>
LOG_FILE="/tmp/openclaw/openclaw-$(date +%F).log"
rg "$TRACE_ID" "$LOG_FILE" | head -n 20
```
