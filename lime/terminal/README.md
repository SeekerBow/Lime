# lime.terminal — 集成终端

用 `QProcess` 托管本机交互式 Shell，键盘事件直接转发到子进程。

## API

- `default_shell() -> (program, args)`
  - Windows：`%COMSPEC%`（通常 `cmd.exe`）；
  - POSIX：`$SHELL` 或 `/bin/bash -i`。
- `strip_ansi(text) -> str`（纯函数）：移除 CSI/OSC/单字节转义、
  响铃，规范化 `CRLF/CR`，模拟退 BS 删除。
- `TerminalWidget(QPlainTextEdit)`
  - `start_shell(shell="")`（空串时读设置/平台默认）、
    `stop_shell()`、`restart_shell()`、`is_running()`；
  - `send_text(text)`、`send_command(cmd)`；
  - 支持 Enter、Backspace、Tab、Esc、方向键、Home/End、
    Delete、PageUp/Down、`Ctrl+C`、`Ctrl+D`、Ctrl+± 缩放；
  - 输出自动清理 ANSI，最多保留 10000 行。

终端 Shell 可在设置中覆盖（如 `powershell`、`C:\\Program Files\\Git\\bin\\bash.exe`）。

## 测试

`tests/test_terminal.py`：ANSI 各类序列清理、默认 Shell 选择、
Windows 下真实启动 `cmd.exe` 执行 `echo` 的往返验证、重启验证
（其他平台自动跳过集成用例）。
