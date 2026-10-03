# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""LSP 服务管理层：多语言服务器、文档生命周期、防抖同步、设置联动。

UI 层只需把文件的 打开/修改/保存/关闭 事件喂给 :class:`LspService`，
诊断经信号原样转发；补全请求按路径路由到对应服务器。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core.settings import Settings
from .client import READY, LspClient
from .protocol import ServerSpec, language_id_for_path, path_to_uri, server_for_path, uri_to_path

#: 修改后多久把变更同步给语言服务器（毫秒）
CHANGE_DEBOUNCE_MS = 300


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


@dataclass
class _Doc:
    path: str
    server_key: str
    uri: str
    language_id: str
    text: str
    version: int = 1


class LspService(QObject):
    #: 诊断更新：(归一化路径, list[Diagnostic])
    diagnosticsReceived = pyqtSignal(str, list)
    #: 补全响应：(请求 id, list[CompletionItem])
    completionReceived = pyqtSignal(int, list)
    #: 服务器状态：(key, 状态文本)
    serverStatus = pyqtSignal(str, str)
    #: 调试/日志
    logReceived = pyqtSignal(str)

    def __init__(
        self,
        settings: Settings,
        command_lookup: Optional[Callable[[str], str]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._command_lookup = command_lookup or (
            lambda key: getattr(self.settings, "clangd_command") if key == "clangd" else key
        )
        self._clients: dict[str, LspClient] = {}
        self._client_roots: dict[str, str] = {}
        self._docs: dict[str, _Doc] = {}
        self._timers: dict[str, QTimer] = {}

    # ---- 对外状态 --------------------------------------------------------
    def enabled(self) -> bool:
        return bool(self.settings.lsp_enabled)

    def is_server_ready(self, key: str) -> bool:
        client = self._clients.get(key)
        return client is not None and client.is_ready()

    def trigger_characters(self, path: str) -> tuple[str, ...]:
        doc = self._docs.get(_norm(path))
        if doc is None:
            return (".", ":", ">", "#")
        client = self._clients.get(doc.server_key)
        return client.completion_triggers if client is not None else (".", ":", ">", "#")

    # ---- 设置变化 --------------------------------------------------------
    def reload(self) -> None:
        """设置改变后：停止现有服务器，并为已打开文件重新握手/同步。"""
        docs = [(doc.path, doc.text) for doc in self._docs.values()]
        self._docs.clear()
        for timer in self._timers.values():
            timer.stop()
        self._timers.clear()
        for client in self._clients.values():
            client.stop()
            client.deleteLater()
        self._clients.clear()
        self._client_roots.clear()
        if not self.enabled():
            return
        # 用最新配置重新打开所有仍在编辑器中的文件
        for path, text in docs:
            self._open_doc(path, text, reopen=True)

    def shutdown(self) -> None:
        for timer in self._timers.values():
            timer.stop()
        for client in self._clients.values():
            client.stop()

    # ---- 文档生命周期 ----------------------------------------------------
    def on_opened(self, path: str, text: str) -> None:
        self._open_doc(path, text, reopen=False)

    def on_changed(self, path: str, text: str) -> None:
        key = _norm(path)
        doc = self._docs.get(key)
        if doc is None:
            # 未跟踪（未启用/不支持）时静默忽略
            return
        doc.text = text
        timer = self._timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._flush_change(k))
            self._timers[key] = timer
        timer.start(CHANGE_DEBOUNCE_MS)

    def on_saved(self, path: str, text: str) -> None:
        key = _norm(path)
        doc = self._docs.get(key)
        if doc is None:
            self.on_opened(path, text)
            return
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.stop()
        doc.text = text
        client = self._clients.get(doc.server_key)
        if client is not None and client.is_ready():
            client.did_save(doc.uri, text)

    def on_closed(self, path: str) -> None:
        key = _norm(path)
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.stop()
        doc = self._docs.pop(key, None)
        if doc is None:
            return
        client = self._clients.get(doc.server_key)
        if client is not None and client.is_ready():
            client.did_close(doc.uri)

    def request_completion(self, path: str, line: int, character: int) -> int:
        doc = self._docs.get(_norm(path))
        if doc is None:
            return -1
        client = self._clients.get(doc.server_key)
        if client is None or not client.is_ready():
            return -1
        return client.request_completion(doc.uri, line, character)

    # ---- 内部 ------------------------------------------------------------
    def _open_doc(self, path: Optional[str], text: str, reopen: bool) -> None:
        if not self.enabled() or not path:
            return
        spec = server_for_path(path)
        if spec is None:
            return
        key = _norm(path)
        existing = self._docs.get(key)
        if existing is not None and not reopen:
            # 已跟踪：直接同步最新内容
            existing.text = text
            client = self._clients.get(existing.server_key)
            if client is not None and client.is_ready():
                existing.version += 1
                client.did_change(existing.uri, text, existing.version)
            return

        client = self._ensure_client(spec, os.path.dirname(path))
        doc = _Doc(
            path=path,
            server_key=spec.key,
            uri=path_to_uri(path),
            language_id=language_id_for_path(path) or "plaintext",
            text=text,
        )
        self._docs[key] = doc
        if client.is_ready():
            client.did_open(doc.uri, doc.language_id, doc.text)

    def _flush_change(self, key: str) -> None:
        doc = self._docs.get(key)
        if doc is None:
            return
        client = self._clients.get(doc.server_key)
        if client is not None and client.is_ready():
            doc.version += 1
            client.did_change(doc.uri, doc.text, doc.version)

    def _ensure_client(self, spec: ServerSpec, root_dir: str) -> LspClient:
        existing = self._clients.get(spec.key)
        if existing is not None:
            return existing
        command = self._command_lookup(spec.key) or spec.key
        client = LspClient(spec.key, command, list(spec.args), root_dir, self)
        client.initialized.connect(lambda k=spec.key: self._on_initialized(k))
        client.failed.connect(lambda msg, k=spec.key: self.serverStatus.emit(k, msg))
        client.logReceived.connect(self.logReceived.emit)
        client.diagnosticsReceived.connect(self._on_diagnostics)
        client.completionReceived.connect(self.completionReceived.emit)
        self._clients[spec.key] = client
        self._client_roots[spec.key] = root_dir
        self.serverStatus.emit(spec.key, f"{spec.display_name} 正在启动…")
        client.start()
        return client

    def _on_initialized(self, key: str) -> None:
        client = self._clients.get(key)
        # 握手完成后把该服务器负责的所有文件重新 did_open
        if client is not None:
            for doc in self._docs.values():
                if doc.server_key == key:
                    doc.version = 1
                    client.did_open(doc.uri, doc.language_id, doc.text)
        self.serverStatus.emit(key, f"{key} 就绪")

    def _on_diagnostics(self, uri: str, diagnostics: list) -> None:
        path = uri_to_path(uri)
        self.diagnosticsReceived.emit(_norm(path), diagnostics)
