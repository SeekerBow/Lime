"""运行输出面板：输出区 + 输入框 + 运行/停止按钮 + 状态标签。"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..terminal.terminal import strip_ansi
from .runner import CodeRunner

_NEWLINE = "\r\n" if sys.platform.startswith("win") else "\n"


class OutputPanel(QWidget):
    """承载 :class:`CodeRunner` 的可见输出。"""

    run_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.runner = CodeRunner(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.run_button = QPushButton("运行 (F5)")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.clear_button = QPushButton("清空")
        self.status_label = QLabel("就绪")
        bar.addWidget(self.run_button)
        bar.addWidget(self.stop_button)
        bar.addWidget(self.clear_button)
        bar.addStretch(1)
        bar.addWidget(self.status_label)
        layout.addLayout(bar)

        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        layout.addWidget(self.output_view)

        # 交互式 stdin 输入框：程序调用 cin/scanf/input() 时在此输入
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("输入"))
        self.input_edit = QLineEdit()
        self.input_edit.setEnabled(False)
        self.input_edit.setPlaceholderText("程序运行需要输入时，在这里输入内容后按回车")
        input_row.addWidget(self.input_edit, 1)
        layout.addLayout(input_row)
        # 点击只读输出区（比如看到 cin 提示）时直接把焦点送进输入框
        self.output_view.installEventFilter(self)

        self.run_button.clicked.connect(self.run_requested)
        self.stop_button.clicked.connect(self.runner.stop)
        self.clear_button.clicked.connect(self.clear)
        self.input_edit.returnPressed.connect(self._send_input)

        self.runner.started.connect(self._append)
        self.runner.output_emitted.connect(self._append)
        self.runner.run_finished.connect(self._on_finished)

    def run_file(self, path: str) -> bool:
        if self.runner.is_running():
            return False
        self.clear()
        ok = self.runner.start(path)
        if ok:
            self.run_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.input_edit.setEnabled(True)
            self.input_edit.setFocus()
            self.status_label.setText("运行中…")
        else:
            self.status_label.setText("该文件类型不支持一键运行")
        return ok

    def clear(self) -> None:
        self.output_view.clear()

    def append_text(self, text: str) -> None:
        self._append(text)

    def text(self) -> str:
        return self.output_view.toPlainText()

    def _append(self, text: str) -> None:
        self.output_view.appendPlainText(strip_ansi(text).rstrip("\r\n"))

    def _send_input(self) -> None:
        text = self.input_edit.text()
        if self.runner.send_input(text + _NEWLINE):
            # 回显用户发送的内容，与终端体验一致
            self._append(text)
        self.input_edit.clear()
        self.input_edit.setFocus()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if obj is self.output_view and event.type() == QEvent.Type.MouseButtonPress:
            if self.runner.is_running():
                self.input_edit.setFocus()
        return False

    def _on_finished(self, code: int, status: str) -> None:
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.input_edit.setEnabled(False)
        self.input_edit.clear()
        label = {
            "normal": f"已结束，退出码 {code}",
            "crashed": f"进程崩溃，退出码 {code}",
            "failed_to_start": "启动失败",
        }.get(status, status)
        self.status_label.setText(label)
        self._append(f"\n[{label}]")
