# lime.lsp — LSP 集成（实时代码解析与智能补全）

基于 [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
的语言服务集成。当前内置 **clangd**（C/C++/Objective-C）；clangd 是可选
外部工具，不随 lime 分发，缺失时只禁用相关能力，不影响编辑器其余功能。

## 组成

| 文件 | 职责 |
| --- | --- |
| `protocol.py` | 纯逻辑（无 Qt）：JSON-RPC 分帧、URI 转换、诊断/补全数据类、服务器注册表 |
| `client.py` | `LspClient`：单个服务器进程（QProcess）、initialize 握手、请求/响应匹配、信号 |
| `service.py` | `LspService`：按语言复用客户端、文档生命周期、修改防抖（300 ms）、设置联动 |
| `completion.py` | 智能补全：无焦点弹窗 `CompletionPopup` 与 `CompletionController` |
| `problems_panel.py` | `ProblemsPanel`：全部打开文件的诊断列表，双击/回车跳转 |

## protocol.py 公开 API

- `encode_message(dict) -> bytes` 与 `MessageFramer.feed(bytes) -> list[dict]`：
  `Content-Length` 分帧，正确处理半包/粘包/非法头；
- `path_to_uri` / `uri_to_path`：Windows 盘符形式
  `file:///E:/dir/x.cpp` 的双向转换；
- `Diagnostic`（0 基行列、`severity_label()`：错误/警告/信息/提示）、
  `TextEdit`、`CompletionItem`（`insert_value` 自动回退 label，
  支持 TextEdit 与 InsertReplaceEdit）；
- `parse_diagnostics(payload)` / `parse_completions(result)`（列表或
  `CompletionList` 两种形态）；
- `server_for_path(path) -> ServerSpec | None`、`language_id_for_path(path)`：
  扩展名注册表（`.c/.h/.cpp/.cc/.cxx/.hpp/.hxx/.m/.mm` → clangd）。

## client / service

- `LspClient(server_key, command, args, root_dir)`：`start()/stop()`、
  `did_open/did_change/did_save/did_close`、`request_completion()`；
  信号 `initialized`、`failed(str)`、`diagnosticsReceived(uri, list)`、
  `completionReceived(id, list)`、`serverStatus`、`logReceived`、`exited`；
  服务器发起的未知客户端请求统一回 `-32601` 错误。
- `LspService(settings, command_lookup=None)`：
  `on_opened/on_changed/on_saved/on_closed(path, text)`、
  `request_completion(path, line, char)`、`trigger_characters(path)`、
  `reload()`（设置保存后重启全部服务器并重放已打开文档）、`shutdown()`。
  clangd 启动参数：`--background-index --clang-tidy --header-insertion=never
  --completion-style=detailed --log=error`。

## 补全交互

- 打字 120 ms 防抖后自动请求；`.`/`->`/`::` 等服务器触发字符立即请求；
  Ctrl+空格强制触发；
- 弹窗为 `Qt.ToolTip` 无焦点窗口，位置跟随光标并自动避免超出屏幕；
- 候选项按“精确前缀 → 忽略大小写 → 包含”排序（上限 60 条），
  ↑↓ 循环、Tab/回车确认、Esc 关闭；
- 插入优先使用服务器返回的 `textEdit` 范围，否则替换当前标识符前缀；
  残留的 snippet 占位符（`${1:x}`/`$0`）会被展平。

## 设置键

- `lsp/enabled`（默认 `True`）
- `lsp/clangd_command`（默认 `clangd`，可填 clangd.exe 完整路径）

未保存的新文档不启动语言服务（LSP 诊断依赖真实文件 URI）；
首次另存落盘后自动 didOpen。

## 测试

`tests/test_lsp_protocol.py` 覆盖分帧（逐字节半包/粘包/非法头）、
URI 往返、数据类解析、注册表与自定义主题；
`tests/test_lsp_integration.py` 包含：

- 用内联 Python 脚本实现的**假 LSP 服务器**做 QProcess 端到端
  （initialize/publishDiagnostics/completion）；
- 不可执行命令的 `failed` 信号；
- `LspService` 文档生命周期与防抖；
- 安装 clangd 时自动启用的**真实 clangd 集成测试**
  （`shutil.which("clangd")` 守卫，验证错误诊断与 `printf` 补全）；
- 补全排序/插入/snippet 展平、弹窗键盘交互、问题面板、编辑器 F8 跳转。
