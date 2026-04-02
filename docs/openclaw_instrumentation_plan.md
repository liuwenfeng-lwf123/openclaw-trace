# OpenClaw 真实埋点方案（Step 2 / MVP）

> 目标：将 T0~T8 接入真实链路事件，并通过 `traceId` 串联前端、网关、Provider、回推与渲染。

## 1) T0~T8 埋点落点（模块 / 函数 / 事件）

| 时间点 | 固定事件名 | 建议模块 | 建议函数/钩子 | 记录时机 |
|---|---|---|---|---|
| T0 | `dashboard.send.click` | dashboard-web | `ChatInput.onSendClick()` | 用户点击发送按钮瞬间 |
| T1 | `dashboard.request.sent` | dashboard-web | `apiClient.sendMessage()` | fetch/xhr 真正发出请求后 |
| T2 | `gateway.message.received` | gateway-api | `POST /v1/chat/messages` 入口中间件 | 网关收到请求并完成 body parse |
| T3 | `gateway.processing.start` | gateway-service | `MessageOrchestrator.handle()` | 从队列取出并开始处理 |
| T4 | `provider.request.start` | gateway-provider | `ProviderClient.stream()` | 向模型 Provider 发起请求前 |
| T5 | `provider.first_token` | gateway-provider | `ProviderStream.onToken()` | 收到第一个 token |
| T6 | `provider.response.complete` | gateway-provider | `ProviderStream.onComplete()` | 收到模型完整结束信号 |
| T7 | `dashboard.push.start` | gateway-push | `PushHub.publish()` | 网关开始向前端推送 |
| T8 | `dashboard.render.done` | dashboard-web | `ChatMessageList.onRenderDone()` | 前端完成最终渲染（含增量收敛） |

## 2) traceId 生成与贯穿

### 生成
- 首选在前端 T0 生成 UUIDv7（或 UUID4 兜底）。
- 字段名固定：`traceId`。

### 传播
- 前端 -> 网关：
  - HTTP Header: `x-trace-id: <traceId>`
  - Body: `traceId`
- 网关内部：
  - 进入请求上下文（request context / MDC）
  - 下游 provider 调用 header 透传 `x-trace-id`
- 网关 -> 前端（SSE/WebSocket）：
  - 每个推送包附带 `traceId`

### 兜底
- 若网关入口无 `traceId`，网关生成并回写响应头 `x-trace-id`。
- 任一模块记录事件时若无 `traceId`，日志照写但打 `traceId="missing"`，分析器应跳过聚合。

## 3) 结构化 JSON 日志格式（单事件）

```json
{
  "ts": "2026-04-01T10:00:00.123Z",
  "level": "INFO",
  "service": "gateway",
  "module": "gateway-provider",
  "function": "ProviderStream.onToken",
  "event": "provider.first_token",
  "traceId": "018f9d3f-0f8d-7f3c-bf2e-8f9fd00a9c91",
  "messageId": "msg_123",
  "sessionId": "sess_abc",
  "userId": "user_01",
  "meta": {
    "model": "gpt-4.1",
    "tokenIndex": 1
  }
}
```

### 必填字段（MVP）
- `ts`, `event`, `traceId`

### 推荐字段（增强）
- `service`, `module`, `function`, `messageId`, `sessionId`, `meta`

## 4) 实时读取器输入约定

- 日志文件采用 **JSON Lines**（每行一个 JSON 事件）。
- 最小事件兼容：
```json
{"ts":"2026-04-01T10:00:00.000Z","event":"dashboard.send.click","traceId":"trace-1"}
```
- 字段别名兼容：
  - 时间：`ts` 或 `timestamp`
  - 事件：`event` 或 `name`

