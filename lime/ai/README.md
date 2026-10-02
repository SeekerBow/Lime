# lime.ai — 本地 Ollama 助手

HTTP 客户端（requests）、后台线程（QThread）、聊天侧边栏三层结构，
默认访问 `http://127.0.0.1:11434`，数据不出本机。

## 组成

### `ollama_client.py`（无 Qt 依赖，可独立测试）

- `OllamaClient(host, timeout, session=None)`
  - `list_models() -> list[str]`：`GET /api/tags`；
  - `chat(messages, model, stream=True)`：`POST /api/chat`，
    NDJSON 流式生成器，逐块 yield `message.content`；
  - `chat_once(messages, model) -> str`：非流式；
  - 网络错误、非 200、坏 JSON 统一抛 `OllamaError`。
  - `session` 可注入，便于用假响应测试。

### `worker.py`

- `ChatWorker(QThread)`：信号 `chunk(str)`、`succeeded(str)`、
  `failed(str)`，支持 `request_stop()` 提前终止。
- `ModelListWorker(QThread)`：信号 `succeeded(list)`、`failed(str)`。

### `ai_sidebar.py`

- 模型下拉 + 刷新；聊天记录气泡渲染（HTML 转义）；
- 流式分片实时追加；发送/停止/清空按钮；
- “附带当前编辑器内容”：选中文本优先，否则附全文（截断 4000 字符），
  通过 system 消息注入；
- `build_messages(prompt)` 为纯逻辑，便于单测；
- Ollama 不可达时错误显示在对话区且不影响编辑器；
- `Ctrl+Enter` 发送。

## 准备本地模型

```bash
ollama pull qwen2.5-coder:7b   # 任选已安装模型
ollama serve                   # 默认监听 127.0.0.1:11434
```

## 测试

`tests/test_ollama_client.py`（假 Session：列表解析、流式 NDJSON、
非流式、500/连接错误/坏 JSON）与 `tests/test_ai_sidebar.py`
（上下文构造、流式成功、失败释放状态、无模型拦截、模型列表刷新）。
