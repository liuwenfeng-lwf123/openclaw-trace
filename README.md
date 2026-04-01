# openclaw-trace

OpenClaw 单条消息全链路时序追踪与延迟分析。

## 最终阶段：接入真实 OpenClaw 运行日志（最小改动版）

### 新增/改动文件
- `gateway/openclaw_gateway.py`：Gateway 真实埋点（T2~T6）。
- `dashboard/src/traceInstrumentation.ts`：Dashboard 前端埋点（T0/T1/T7/T8）。
- `src/openclaw_jsonl_logger.py`：统一 JSONL 日志输出函数。
- `src/realtime_log_reader.py`：可直接读取 `logs/openclaw-runtime.jsonl`。
- `src/simulate_openclaw_runtime.py`：最小可运行模拟，生成一条完整链路日志。

### JSONL 统一格式

每条日志统一：

```json
{
  "ts": "2026-04-01T10:00:00.123Z",
  "traceId": "trace-xxx",
  "event": "provider.first_token",
  "module": "gateway"
}
```

### 埋点事件映射

- Dashboard：
  - `dashboard.send.click` (T0)
  - `dashboard.request.sent` (T1)
  - `dashboard.push.start` (T7)
  - `dashboard.render.done` (T8)
- Gateway：
  - `gateway.message.received` (T2)
  - `gateway.processing.start` (T3)
  - `provider.request.start` (T4)
  - `provider.first_token` (T5)
  - `provider.response.complete` (T6)

### 本地最小运行

```bash
# 1) 生成真实格式运行日志
: > logs/openclaw-runtime.jsonl
python3 src/simulate_openclaw_runtime.py

# 2) 直接读取 OpenClaw 日志（从文件开头）
python3 src/realtime_log_reader.py logs/openclaw-runtime.jsonl --from-beginning --idle-flush-sec 1
```

### Reader 稳健性
- 缺 `event`：忽略该行
- 缺 `ts`：自动补当前 UTC
- 缺 `traceId`：不参与 trace 聚合
