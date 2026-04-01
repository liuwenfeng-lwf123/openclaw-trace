# OpenClaw Web 实时监控（当前验收修复）

## 本轮只修：实时监听失效闭环
真实日志新增 -> reader 解析 -> runId/traceId 聚合 -> ws 广播 -> 前端新增记录。

## 本轮改动文件

### 1) `src/openclaw_event_adapter.py`
**作用**：真实日志格式适配，runId 优先接入。
- 兼容 `{"0":"...","1":{...},"_meta":{...},"time":"..."}`。
- `1` 为对象时优先提取：`event/runId/tags/error/provider/model`。
- `1` 为字符串时做文本匹配。
- 聚合主键优先级：
  `traceId -> trace_id -> x_trace_id -> x-trace-id -> runId -> _meta.request_id -> message_id -> conversation_id`。

### 2) `src/realtime_log_reader.py`
**作用**：按主键聚合真实链路并输出调试日志。
- 打印：开文件成功、读行计数、解析成功/失败、跳过原因、最终聚合键类型。
- 跳过原因：`invalid_json/not_dict/adapter_no_event/missing_trace_id/empty_line`。
- 结果状态：`ok/error/timeout`。
- 每条结果附带：`event_timeline/provider/model/error_reason/group_key_type`。

### 3) `backend/ws_bridge.py`
**作用**：确认 ws 层是否收到 reader 数据并成功广播。
- 打印：ws 启动、client 连接、reader 输入、broadcast 准备/成功/失败。

### 4) `web/src/App.jsx`
**作用**：前端实时验收可视化。
- 打印：ws connect/open/close/error、payload、state 更新。
- 自动选中最新记录。
- 列表/详情显示：ID（runId或traceId）、status、error_reason、provider/model、event timeline。
- 图上仍显示 missing、最慢边高亮、每段 ms。

## 真实日志字段规则（当前实现）

1. 事件识别：
- 优先：`1.event`（当 `1` 是对象）
- 其次：`event/name/stage/_meta.event/_meta.event_name`
- 再其次：文本匹配（含 `model_fallback_decision/embedded_run_agent_end/live session model switch/recall failed/timeout/rate limit/http 401/econnrefused`）

2. 聚合键提取：
- `traceId -> trace_id -> x_trace_id -> x-trace-id -> runId -> _meta.request_id -> message_id -> conversation_id`

3. 无法聚合时：
- 返回 `missing` 并跳过，reader debug 会打印原因。

## 本机验证命令（真实路径）

```bash
export OPENCLAW_TRACE_DEBUG=1
LOG_FILE="/tmp/openclaw/openclaw-$(date +%F).log"
python3 backend/ws_bridge.py --log-file "$LOG_FILE" --tail
```

```bash
cd web
npm install
npm run dev
```

### 验证点
1) 真实 OpenClaw 发消息后，左侧新增记录（ID 可是 runId 或 traceId）
2) 默认选中新记录，右侧详情刷新
3) event timeline 可看到真实事件顺序
4) 若异常/超时，status 显示 `error/timeout`
5) trace/run 与日志行对齐：

```bash
ID=<页面新出现ID>
rg "$ID" "/tmp/openclaw/openclaw-$(date +%F).log" | head -n 20
```

## 排障（你现在这个“页面无新增”场景）

若页面 `WS: connected` 但列表仍空：

1. 先看后端是否持续出现：
- `[reader-debug] tail_idle waiting_new_line ...`
- 如果只有 idle，没有 `line_read_count`，说明当前监听文件没有新增行。

2. 当前 reader 会自动切换到同目录最新 `openclaw-*.log`，启动时会打印：
- `[reader-debug] log_target_switched old=... new=...`

3. 若仍无 `line_parsed_ok`：
- 看是否一直 `line_skipped reason=...`
- 贴出前 5 条 skipped 原因即可继续定位。

4. 若有 `line_parsed_ok` 但页面不更新：
- 看 `ws-debug` 是否有 `broadcast_prepare` / `broadcast_done`
- 看浏览器 console 是否有 `[ui-ws] payload` 与 `[ui-state] trace_update`
