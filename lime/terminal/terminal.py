"""集成终端：用 :class:`QProcess` 托管本机交互式 Shell。

键盘事件被转发到子进程，输出回流到只读文本区。ANSI 转义序列在显示前
由 :func:`strip_ansi` 清理（该函数为纯函数，可独立单测）。
"""

from __future__ import annotations

import locale
import os
import re
import sys

from PyQt6.QtCore import Qt, QProcess, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings

# CSI：ESC [ 参数 中间字节 终止字节
_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# OSC：ESC ] ... BEL 或 ESC \
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
# 单字节转义（如 ESC = 、ESC D 换行）
_SINGLE_RE = re.compile(r"\x1b[@-Z\\-_]")
_BELL_RE = re.compile(r"\x07")


def encode_process_input(text: str) -> bytes:
    """编码发往子进程 stdin 的用户输入。

    Windows 管道没有控制台代码页上下文，教学场景的 C/C++ ``cin``、
    Python ``input()`` 普遍按系统 ANSI 代码页（中文系统为 GBK/CP936）
    解析字节，因此 Windows 优先 ``mbcs``；POSIX 优先 UTF-8。
    按候选链严格编码，latin-1 兜底。
    """
    if sys.platform.startswith("win"):
        candidates = ["mbcs", "cp936", locale.getpreferredencoding(False), "utf-8"]
    else:
        candidates = ["utf-8", locale.getpreferredencoding(False)]
    tried: set[str] = set()
    for encoding in candidates:
        if not encoding or encoding in tried:
            continue
        tried.add(encoding)
        try:
            return text.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            continue
    return text.encode("latin-1", errors="replace")


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


class TerminalView(QPlainTextEdit):
    """终端只读输出区；点击它时把焦点交还给下方输入框。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().mousePressEvent(event)
        self.clicked.emit()


class TerminalInputEdit(QPlainTextEdit):
    """终端命令输入框：Enter 发送，Shift/Ctrl+Enter 在框内换行。"""

    submitted = pyqtSignal()
    interrupt_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        # Ctrl+C：有选中文字时执行复制，否则向 Shell 发送中断（Ctrl+C）
        if ctrl and key == Qt.Key.Key_C and not self.textCursor().hasSelection():
            self.interrupt_requested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Shift/Ctrl+Enter 走默认行为（插入换行），普通 Enter 发送
            if not (
                modifiers & Qt.KeyboardModifier.ShiftModifier
                or modifiers & Qt.KeyboardModifier.ControlModifier
            ):
                self.submitted.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class TerminalWidget(QWidget):
    """嵌入式终端：上方只读输出区 + 下方命令输入框。"""

    def __init__(self, settings: Settings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        font = QFont("Consolas", 10)

        self.view = TerminalView(self)
        self.view.setReadOnly(True)
        self.view.setFont(font)
        self.view.setUndoRedoEnabled(False)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.view.document().setMaximumBlockCount(10000)
        self.view.clicked.connect(self.setFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(4, 2, 4, 4)
        input_row.addWidget(QLabel("输入"))
        self.input_edit = TerminalInputEdit(self)
        self.input_edit.setFont(font)
        self.input_edit.setUndoRedoEnabled(False)
        self.input_edit.setEnabled(False)
        self.input_edit.setPlaceholderText(
            "输入命令后按回车发送；Shift+回车换行（多行内容将一起发送）"
        )
        # 固定约 3 行高度，容纳多行待发命令
        line_height = self.input_edit.fontMetrics().lineSpacing()
        self.input_edit.setFixedHeight(line_height * 3 + 12)
        input_row.addWidget(self.input_edit, 1)
        layout.addLayout(input_row)

        self.input_edit.submitted.connect(self._submit_input)
        self.input_edit.interrupt_requested.connect(lambda: self.send_text("\x03"))

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self._on_started)
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
        self.input_edit.clear()
        self.start_shell()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def send_text(self, text: str) -> None:
        """向 Shell 发送原始文本（不保证带回车）。"""
        if self.is_running():
            self.process.write(encode_process_input(text))

    def send_command(self, command: str) -> None:
        """发送一整条命令并回车。"""
        self.send_text(command + self._newline)

    def clear_terminal(self) -> None:
        self.clear()

    # ---- 与旧接口/外部调用保持兼容 --------------------------------------
    def toPlainText(self) -> str:  # noqa: N802 (与 Qt 命名一致)
        return self.view.toPlainText()

    def clear(self) -> None:
        self.view.clear()

    def setFocus(self, reason=Qt.FocusReason.OtherFocusReason) -> None:  # noqa: N802
        # 焦点一律进入命令输入框
        self.input_edit.setFocus()

    # ---- 输入框提交 ------------------------------------------------------
    def _submit_input(self) -> None:
        if not self.is_running():
            return
        # 统一换行：多行内容按行依次发送（Shell 会逐行执行），末尾补回车
        text = self.input_edit.toPlainText()
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        if text:
            self.send_text(text.replace("\n", self._newline) + self._newline)
        else:
            self.send_text(self._newline)
        self.input_edit.clear()

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
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(cleaned)
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()

    def _on_started(self) -> None:
        self._append_raw("[终端已启动]\n")
        self.input_edit.setEnabled(True)
        self.input_edit.setFocus()

    def _on_finished(self, code: int, _status) -> None:
        self._append_raw(f"\n[终端已退出，退出码 {code}]\n")
        self.input_edit.setEnabled(False)
        self.input_edit.clear()
