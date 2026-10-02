"""集成终端：用 :class:`QProcess` 托管本机交互式 Shell。

键盘事件被转发到子进程，输出回流到只读文本区。ANSI 转义序列在显示前
由 :func:`strip_ansi` 清理（该函数为纯函数，可独立单测）。
"""

from __future__ import annotations

import locale
import os
import re
import sys

from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from ..core.settings import Settings

# CSI：ESC [ 参数 中间字节 终止字节
_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# OSC：ESC ] ... BEL 或 ESC \
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
# 单字节转义（如 ESC = 、ESC D 换行）
_SINGLE_RE = re.compile(r"\x1b[@-Z\\-_]")
_BELL_RE = re.compile(r"\x07")


def decode_process_bytes(data: bytes) -> str:
    """解码子进程输出：按候选编码依次严格尝试。

    UTF-8 优先；中文 Windows 上 javac/gcc 等工具的诊断信息按 GBK/CP936
    输出（Python 3.14 的 getpreferredencoding 已默认 UTF-8，不能再依赖
    它回退），因此候选链显式包含 ``mbcs``/``cp936``；latin-1 兜底。
    GBK 字节流几乎不可能恰好是合法 UTF-8，回退判定可靠。
    """
    candidates = [
        "utf-8",
        locale.getpreferredencoding(False),
        "mbcs",
        "cp936",
        "latin-1",
    ]
    tried: set[str] = set()
    for encoding in candidates:
        if not encoding or encoding in tried:
            continue
        tried.add(encoding)
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    """移除常见 ANSI 转义序列、响铃，规范化换行并模拟退格。"""
    text = _OSC_RE.sub("", text)
    text = _CSI_RE.sub("", text)
    text = _SINGLE_RE.sub("", text)
    text = _BELL_RE.sub("", text)
    # 模拟退格：字符 + BS => 删除该字符
    while "\x08" in text:
        new_text = re.sub(r"[^\n]\x08", "", text, count=1)
        if new_text == text:
            new_text = text.replace("\x08", "", 1)
        text = new_text
    text = text.replace("\r\n", "\n").replace("\r", "")
    return text


def default_shell() -> tuple[str, list[str]]:
    """返回当前平台默认 Shell 的 ``(程序, 参数)``。"""
    if sys.platform.startswith("win"):
        return os.environ.get("COMSPEC", "cmd.exe"), []
    shell = os.environ.get("SHELL", "/bin/bash")
    return shell, ["-i"]


class TerminalWidget(QPlainTextEdit):
    """简易嵌入式终端。"""

    def __init__(self, settings: Settings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 10))
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.document().setMaximumBlockCount(10000)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(lambda: self._append_raw("[终端已启动]\n"))
        self.process.finished.connect(self._on_finished)

        self._newline = "\r\n" if sys.platform.startswith("win") else "\n"

    # ---- 生命周期 --------------------------------------------------------
    def start_shell(self, shell: str = "") -> bool:
        """启动 Shell；显式传 ``shell``，否则读设置/平台默认。"""
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return True
        override = shell or (self.settings.terminal_shell if self.settings else "")
        if override:
            program, args = override, []
        else:
            program, args = default_shell()
        self._newline = "\r\n" if (
            program.lower().endswith("cmd.exe") or program.lower().endswith("cmd")
        ) else "\n"
        if program == "powershell" or program.endswith("powershell.exe"):
            args = ["-NoLogo"]
        self.process.start(program, args)
        return self.process.waitForStarted(3000)

    def stop_shell(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

    def restart_shell(self) -> None:
        self.stop_shell()
        self.clear()
        self.start_shell()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def send_text(self, text: str) -> None:
        """向 Shell 发送原始文本（不保证带回车）。"""
        if self.is_running():
            self.process.write(text.encode("utf-8", errors="replace"))

    def send_command(self, command: str) -> None:
        """发送一整条命令并回车。"""
        self.send_text(command + self._newline)

    def clear_terminal(self) -> None:
        self.clear()

    # ---- 输出 ------------------------------------------------------------
    def _read_output(self) -> None:
        data = bytes(self.process.readAllStandardOutput())
        if not data:
            return
        self._append_raw(decode_process_bytes(data))

    def _append_raw(self, text: str) -> None:
        cleaned = strip_ansi(text)
        if not cleaned:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(cleaned)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _on_finished(self, code: int, _status) -> None:
        self._append_raw(f"\n[终端已退出，退出码 {code}]\n")

    # ---- 键盘转发 --------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        if not self.is_running():
            return
        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        if ctrl and key == Qt.Key.Key_C:
            self.send_text("\x03")
            return
        if ctrl and key == Qt.Key.Key_D:
            self.send_text("\x04")
            return
        if ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoomIn(1)
            return
        if ctrl and key == Qt.Key.Key_Minus:
            self.zoomOut(1)
            return

        special = {
            Qt.Key.Key_Return: self._newline,
            Qt.Key.Key_Enter: self._newline,
            Qt.Key.Key_Backspace: "\x08",
            Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Escape: "\x1b",
            Qt.Key.Key_Up: "\x1b[A",
            Qt.Key.Key_Down: "\x1b[B",
            Qt.Key.Key_Right: "\x1b[C",
            Qt.Key.Key_Left: "\x1b[D",
            Qt.Key.Key_Home: "\x1b[H",
            Qt.Key.Key_End: "\x1b[F",
            Qt.Key.Key_Delete: "\x1b[3~",
            Qt.Key.Key_PageUp: "\x1b[5~",
            Qt.Key.Key_PageDown: "\x1b[6~",
        }
        if key in special:
            self.send_text(special[key])
            return

        text = event.text()
        if text and not ctrl:
            self.send_text(text)

    # ---- 鼠标：保留选择能力，但输入时光标自动回到底部 ----------------------
    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().focusInEvent(event)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
