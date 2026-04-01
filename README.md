# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析（MVP）。

## 当前最小可运行版（Step 1）

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

能力：
- 基于 `traceId` 聚合单条消息。
- 自动识别最慢环节，并红色高亮输出。
- 计算最慢环节占全链路比例。
- 给出原因提示。
- 缺失时间点不崩溃，输出 `missing`。

## 运行

```bash
python3 src/trace_analyzer.py examples/sample_trace.json
```

## 输入格式

```json
{
  "traceId": "trace-xxx",
  "events": [
    {"name": "dashboard.send.click", "timestamp": "2026-04-01T10:00:00.000Z"}
  ]
}
```

> 时间戳支持 ISO8601，未带时区时默认按 UTC。
