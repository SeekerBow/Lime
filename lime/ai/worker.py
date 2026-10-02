"""Ollama 后台线程，避免网络请求阻塞 UI。"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from .ollama_client import OllamaClient, OllamaError


class ChatWorker(QThread):
    """流式对话线程。"""

    chunk = pyqtSignal(str)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: OllamaClient,
        model: str,
        messages: list[dict],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._model = model
        self._messages = messages
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:  # noqa: N802 (Qt API)
        parts: list[str] = []
        try:
            for delta in self._client.chat(self._messages, self._model, stream=True):
                if self._stop_requested:
                    break
                parts.append(delta)
                self.chunk.emit(delta)
        except OllamaError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - 线程内兜底，绝不让应用崩溃
            self.failed.emit(f"AI 请求发生未知错误：{exc}")
            return
        self.succeeded.emit("".join(parts))


class ModelListWorker(QThread):
    """拉取模型列表的线程。"""

    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, client: OllamaClient, parent=None) -> None:
        super().__init__(parent)
        self._client = client

    def run(self) -> None:  # noqa: N802 (Qt API)
        try:
            models = self._client.list_models()
        except OllamaError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"获取模型列表失败：{exc}")
            return
        self.succeeded.emit(models)
