"""ai.ai_sidebar 单元测试：消息构造、流式渲染、失败处理、模型列表。"""

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from lime.ai.ai_sidebar import AISidebar


class FakeChatWorker(QObject):
    chunk = pyqtSignal(str)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, deltas=(), error=None, parent=None):
        super().__init__(parent)
        self._deltas = deltas
        self._error = error
        self.stop_requested = False

    def start(self):
        if self._error:
            self.failed.emit(self._error)
            return
        for delta in self._deltas:
            self.chunk.emit(delta)
        self.succeeded.emit("".join(self._deltas))

    def request_stop(self):
        self.stop_requested = True


class FakeListWorker(QObject):
    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, models, parent=None):
        super().__init__(parent)
        self._models = models

    def start(self):
        self.succeeded.emit(self._models)


@pytest.fixture
def sidebar(qapp, settings):
    settings.ollama_model = ""
    bar = AISidebar(settings, auto_refresh=False)
    bar.model_combo.addItem("test-model")
    bar.model_combo.setCurrentText("test-model")
    return bar


def test_build_messages_without_context(sidebar):
    sidebar.context_box.setChecked(False)
    messages = sidebar.build_messages("你好")
    assert messages == [{"role": "user", "content": "你好"}]


def test_build_messages_with_selection_context(sidebar):
    sidebar.set_editor_context("main.py", "whole-content", "print(1)")
    messages = sidebar.build_messages("解释这段代码")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "main.py" in messages[0]["content"]
    assert "print(1)" in messages[0]["content"]
    # 有选中文本时不带全文
    assert "whole-content" not in messages[0]["content"]
    assert messages[-1]["content"] == "解释这段代码"


def test_build_messages_with_full_file_context(sidebar):
    sidebar.set_editor_context("a.py", "X = 1", "")
    messages = sidebar.build_messages("看一下")
    assert "X = 1" in messages[0]["content"]


def test_send_streaming_success(sidebar):
    captured = {}

    def factory(model, messages):
        captured["model"] = model
        captured["messages"] = messages
        return FakeChatWorker(["He", "llo"], parent=sidebar)

    sidebar._make_chat_worker = factory
    sidebar.input_edit.setPlainText("hi")
    sidebar.send()

    assert captured["model"] == "test-model"
    assert sidebar.history()[-1] == {"role": "assistant", "content": "Hello"}
    assert "Hello" in sidebar.chat_view.toPlainText()
    assert sidebar.send_button.isEnabled() is True
    assert sidebar.stop_button.isEnabled() is False


def test_send_failure_releases_busy_state(sidebar):
    errors = []
    sidebar.status_message.connect(errors.append)

    sidebar._make_chat_worker = lambda model, messages: FakeChatWorker(
        error="connection refused", parent=sidebar
    )
    sidebar.input_edit.setPlainText("hi")
    sidebar.send()

    assert sidebar.send_button.isEnabled() is True
    assert any("connection refused" in e for e in errors)
    assert "connection refused" in sidebar.chat_view.toPlainText()


def test_send_without_model_ignored(qapp, settings):
    settings.ollama_model = ""
    bar = AISidebar(settings, auto_refresh=False)  # 无任何模型
    messages_status = []
    bar.status_message.connect(messages_status.append)
    bar.input_edit.setPlainText("hi")
    bar.send()
    assert bar.history() == []
    assert any("模型" in m for m in messages_status)


def test_clear_history(sidebar):
    sidebar._history = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    sidebar.clear_history()
    assert sidebar.history() == []


def test_refresh_models_populates_combo(sidebar):
    sidebar._make_list_worker = lambda: FakeListWorker(["a:1", "b:2"], sidebar)
    sidebar.refresh_models()
    assert [sidebar.model_combo.itemText(i) for i in range(2)] == ["a:1", "b:2"]
    assert sidebar.refresh_button.isEnabled() is True
