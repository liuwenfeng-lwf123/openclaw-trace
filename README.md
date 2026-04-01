# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析。

## Step 1：离线单条 Trace 分析器（已完成）

已实现固定 9 个事件点：
- T0 = `dashboard.send.click`
- T1 = `dashboard.request.sent`
- T2 = `gateway.message.received`
- T3 = `gateway.processing.start`
- T4 = `provider.request.start`
- T5 = `provider.first_token`
- T6 = `provider.response.complete`
- T7 = `dashboard.push.start`
- T8 = `dashboard.render.done`

并计算以下时延：
- T1-T0, T2-T1, T3-T2, T4-T3, T5-T4, T6-T5, T7-T6, T8-T7
- T5-T0（首响应总时间）
- T8-T0（全链路总耗时）

运行：

```bash
python3 src/trace_analyzer.py examples/sample_trace.json
```

## Step 2：真实数据接入（最小可运行版）

新增：
- `docs/openclaw_instrumentation_plan.md`：真实埋点方案（模块/函数/事件、traceId 贯穿、结构化日志格式）。
- `src/realtime_log_reader.py`：实时 JSONL 日志读取器，持续 tail 文件，自动按 traceId 聚合并调用分析器输出结果。
- `examples/logs/sample_stream.jsonl`：可直接演示的流式日志样例。

运行实时读取器（示例）：

```bash
# 终端1：启动 reader（会持续监听）
python3 src/realtime_log_reader.py examples/logs/live.jsonl --idle-flush-sec 3

# 终端2：模拟日志不断写入
cat examples/logs/sample_stream.jsonl >> examples/logs/live.jsonl
```

在非交互环境可用 `timeout` 演示：

```bash
: > examples/logs/live.jsonl
(timeout 2s python3 src/realtime_log_reader.py examples/logs/live.jsonl --idle-flush-sec 1 &) \
  && sleep 0.2 \
  && cat examples/logs/sample_stream.jsonl >> examples/logs/live.jsonl \
  && wait || true
```

## 输入日志格式（JSON Lines）

最小字段：

```json
{"ts":"2026-04-01T10:00:00.000Z","event":"dashboard.send.click","traceId":"trace-1"}
```

字段兼容：
- 时间：`ts` 或 `timestamp`
- 事件：`event` 或 `name`

缺字段策略：
- 缺 `event`：丢弃该行
- 缺 `ts`：用当前 UTC 时间补齐
- 缺 `traceId`：标记为 `missing` 且不参与聚合
