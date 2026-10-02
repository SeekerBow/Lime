"""AI 侧边栏：模型选择、流式聊天、附带编辑器上下文。"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings
from .ollama_client import OllamaClient
from .worker import ChatWorker, ModelListWorker


@dataclass
class EditorContext:
    """当前编辑器上下文快照。"""

    filename: str = ""
    content: str = ""
    selection: str = ""

    def is_empty(self) -> bool:
        return not (self.content or self.selection)

    def render(self) -> str:
        parts = []
        if self.filename:
            parts.append(f"文件：{self.filename}")
        if self.selection:
            parts.append(f"用户选中的代码：\n```\n{self.selection}\n```")
        if self.content and not self.selection:
            preview = self.content
            if len(preview) > 4000:
                preview = preview[:4000] + "\n...（内容已截断）"
            parts.append(f"当前文件完整内容：\n```\n{preview}\n```")
        return "\n\n".join(parts)


class AISidebar(QWidget):
    """Ollama 聊天侧边栏。"""

    status_message = pyqtSignal(str)

    def __init__(
        self,
        settings: Settings,
        client: Optional[OllamaClient] = None,
        parent: QWidget | None = None,
        auto_refresh: bool = True,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.client = client or OllamaClient(
            host=settings.ollama_host, timeout=settings.ollama_timeout
        )
        self._context = EditorContext()
        self._history: list[dict] = []
        self._worker: Optional[ChatWorker] = None
        self._list_worker: Optional[ModelListWorker] = None
        self._streaming = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        title = QLabel("AI 助手（本地 Ollama）")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(120)
        self.refresh_button = QPushButton("刷新")
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.refresh_button)
        layout.addLayout(model_row)

        # 显示当前连接地址，连不上时方便排查
        self.host_label = QLabel()
        self.host_label.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(self.host_label)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setPlaceholderText("向本地模型提问，例如解释选中代码……")
        layout.addWidget(self.chat_view, 1)

        self.context_box = QCheckBox("附带当前编辑器内容")
        self.context_box.setChecked(True)
        layout.addWidget(self.context_box)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("输入问题，Ctrl+Enter 发送")
        self.input_edit.setFixedHeight(86)
        layout.addWidget(self.input_edit)

        button_row = QHBoxLayout()
        self.send_button = QPushButton("发送")
        self.stop_button = QPushButton("停止")
        self.clear_button = QPushButton("清空对话")
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.send_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.clear_button)
        layout.addLayout(button_row)

        self.send_button.clicked.connect(self.send)
        self.stop_button.clicked.connect(self.stop)
        self.clear_button.clicked.connect(self.clear_history)
        self.refresh_button.clicked.connect(self.refresh_models)

        # 恢复设置中保存的模型
        saved = settings.ollama_model
        if saved:
            self.model_combo.addItem(saved)
            self.model_combo.setCurrentText(saved)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self._refresh_host_label()
        self._render_hint()

        # 启动后自动拉取一次模型列表（异步，不阻塞界面）
        if auto_refresh:
            QTimer.singleShot(0, self.refresh_models)

    def _refresh_host_label(self) -> None:
        self.host_label.setText(f"连接：{self.client.host}")

    def reload_client(self) -> None:
        """设置变化后按最新 host/timeout 重建客户端。"""
        self.client = OllamaClient(
            host=self.settings.ollama_host, timeout=self.settings.ollama_timeout
        )
        self._refresh_host_label()

    # ---- 上下文 ----------------------------------------------------------
    def set_editor_context(self, filename: str, content: str, selection: str) -> None:
        self._context = EditorContext(filename, content, selection)

    def editor_context(self) -> EditorContext:
        return self._context

    def history(self) -> list[dict]:
        return list(self._history)

    # ---- 消息构造（纯逻辑，便于测试）--------------------------------------
    def build_messages(self, prompt: str) -> list[dict]:
        messages: list[dict] = []
        if self.context_box.isChecked() and not self._context.is_empty():
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "你是代码编辑器 lime 内置的编程助手，基于用户给出的代码上下文"
                        "简洁准确地回答。\n\n" + self._context.render()
                    ),
                }
            )
        messages.extend(self._history)
        messages.append({"role": "user", "content": prompt})
        return messages

    # ---- 模型列表 --------------------------------------------------------
    def refresh_models(self) -> None:
        self.refresh_button.setEnabled(False)
        self.status_message.emit("正在获取 Ollama 模型列表…")
        self._list_worker = self._make_list_worker()
        self._list_worker.succeeded.connect(self._on_models)
        self._list_worker.failed.connect(self._on_models_failed)
        self._list_worker.start()

    def _make_list_worker(self) -> ModelListWorker:
        return ModelListWorker(self.client, self)

    def _on_models(self, models: list) -> None:
        self.refresh_button.setEnabled(True)
        current = self.model_combo.currentText()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current:
            idx = self.model_combo.findText(current)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)
        self.status_message.emit(f"发现 {len(models)} 个本地模型")

    def _on_models_failed(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        hint = (
            f"{message}\n请确认 Ollama 已启动（`ollama serve`）且地址正确，"
            f"可在“设置”中修改 Ollama 地址。"
        )
        self.status_message.emit(hint)
        self.chat_view.setHtml(
            f'<p style="color:#c0392b;"><b>无法获取模型列表</b></p>'
            f'<p style="color:#c0392b;">{html.escape(message)}</p>'
            "<p>请确认本地 Ollama 已启动（命令：<code>ollama serve</code>），"
            "并在“设置”中核对 Ollama 地址。</p>"
        )

    def _on_model_changed(self, text: str) -> None:
        if text:
            self.settings.ollama_model = text

    # ---- 发送 ------------------------------------------------------------
    def send(self) -> None:
        if self._streaming:
            return
        prompt = self.input_edit.toPlainText().strip()
        if not prompt:
            return
        model = self.model_combo.currentText().strip()
        if not model:
            self.status_message.emit("请先选择模型（点击“刷新”获取本地模型）")
            return

        messages = self.build_messages(prompt)
        self._history.append({"role": "user", "content": prompt})
        self._refresh_view()
        self.input_edit.clear()
        self._set_busy(True)
        self._stream_buffer = ""

        self._worker = self._make_chat_worker(model, messages)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _make_chat_worker(self, model: str, messages: list[dict]) -> ChatWorker:
        return ChatWorker(self.client, model, messages, self)

    def stop(self) -> None:
        if self._worker is not None and self._streaming:
            self._worker.request_stop()
            self.status_message.emit("正在停止…")

    def clear_history(self) -> None:
        self._history.clear()
        self.chat_view.clear()
        self._render_hint()

    # ---- 流式回调 --------------------------------------------------------
    def _on_chunk(self, delta: str) -> None:
        self._stream_buffer += delta
        self._render_streaming()

    def _on_succeeded(self, full_text: str) -> None:
        text = full_text or self._stream_buffer
        self._history.append({"role": "assistant", "content": text})
        self._set_busy(False)
        self._refresh_view()
        self.status_message.emit("AI 回答完成")

    def _on_failed(self, message: str) -> None:
        error_html = (
            '<p style="color:#c0392b;"><b>错误：</b>'
            f"{html.escape(message)}</p>"
        )
        self._refresh_view(error_html)
        self._set_busy(False)
        self.status_message.emit(message)

    def _set_busy(self, busy: bool) -> None:
        self._streaming = busy
        self.send_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.input_edit.setEnabled(not busy)

    # ---- 渲染 ------------------------------------------------------------
    def _render_hint(self) -> None:
        self.chat_view.setHtml(
            '<p style="color:#888;">在下方输入问题开始对话。'
            '勾选“附带当前编辑器内容”可把当前文件/选中文本发给模型。</p>'
        )

    def _refresh_view(self, extra: str = "") -> None:
        """按历史记录重绘；``extra`` 为流式气泡或错误片段。"""
        if not self._history and not extra:
            self._render_hint()
            return
        body = "".join(
            self._render_message(item["role"], item["content"]) for item in self._history
        )
        body += extra
        self.chat_view.setHtml(body)
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    def _render_streaming(self) -> None:
        # 历史 + 正在生成的助手气泡
        self._refresh_view(self._render_message("assistant", self._stream_buffer))

    @staticmethod
    def _render_message(role: str, content: str) -> str:
        escaped = html.escape(content).replace("\n", "<br/>")
        if role == "user":
            return (
                '<p style="background:#e8f0fe;border-radius:6px;padding:6px;margin:6px 0;">'
                f'<b>我：</b><br/>{escaped}</p>'
            )
        return (
            '<p style="background:#f4f4f4;border-radius:6px;padding:6px;margin:6px 0;">'
            f'<b>AI：</b><br/>{escaped}</p>'
        )

    # ---- 快捷键：Ctrl+Enter 发送 -----------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.send()
            return
        super().keyPressEvent(event)
