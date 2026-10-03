# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""单个语言服务器进程的 LSP 连接。

用 :class:`QProcess` 承载服务器（clangd …），通过 stdin/stdout 交换
带 ``Content-Length`` 分帧的 JSON-RPC 2.0 消息。请求/响应按 id 匹配，
诊断与补全结果通过 Qt 信号抛给上层。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from .protocol import (
    MessageFramer,
    client_completion_capabilities,
    encode_message,
    parse_completions,
    parse_diagnostics,
    path_to_uri,
)

# 状态
STARTING = "starting"
READY = "ready"
FAILED = "failed"
STOPPED = "stopped"


class LspClient(QObject):
    #: initialize 握手完成
    initialized = pyqtSignal()
    #: 服务器无法启动或异常退出
    failed = pyqtSignal(str)
    #: ``(uri, list[Diagnostic])`` 实时诊断
    diagnosticsReceived = pyqtSignal(str, list)
    #: ``(请求 id, list[CompletionItem])`` 补全响应
    completionReceived = pyqtSignal(int, list)
    #: 日志/通知消息
    logReceived = pyqtSignal(str)
    #: 进程结束（退出码）
    exited = pyqtSignal(int)

    def __init__(
        self,
        server_key: str,
        command: str,
        args: list[str],
        root_dir: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.server_key = server_key
        self.command = command
        self.args = list(args)
        self.root_dir = root_dir
        self.state = STARTING
        self.completion_triggers: tuple[str, ...] = (".", ":", ">", "#", "<")

        self._process: Optional[QProcess] = None
        self._framer = MessageFramer()
        self._next_id = 0
        self._request_kinds: dict[int, str] = {}

    # ---- 生命周期 --------------------------------------------------------
    def start(self) -> None:
        if self._process is not None:
            return
        process = QProcess(self)
        process.setProgram(self.command)
        process.setArguments(self.args)
        if os.path.isdir(self.root_dir):
            process.setWorkingDirectory(self.root_dir)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.started.connect(self._on_started)
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(self._on_finished)
        self._process = process
        process.start()

    def stop(self) -> None:
        """终止服务器进程。"""
        if self._process is None:
            self.state = STOPPED
            return
        proc = self._process
        self.state = STOPPED
        try:
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(2000)
        except Exception:  # noqa: BLE001 - 关闭路径不应抛出
            pass

    def is_ready(self) -> bool:
        return self.state == READY

    # ---- 文档同步（TextDocumentSyncKind.Full = 1）-----------------------
    def did_open(self, uri: str, language_id: str, text: str) -> None:
        self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                }
            },
        )

    def did_change(self, uri: str, text: str, version: int) -> None:
        self._notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    def did_save(self, uri: str, text: str) -> None:
        self._notify("textDocument/didSave", {"textDocument": {"uri": uri}, "text": text})

    def did_close(self, uri: str) -> None:
        self._notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    # ---- 请求 ------------------------------------------------------------
    def request_completion(self, uri: str, line: int, character: int) -> int:
        """发起补全请求，返回请求 id（未就绪返回 -1）。"""
        if not self.is_ready():
            return -1
        req_id = self._send_request(
            "completion",
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        return req_id

    # ---- 内部：进程事件 ---------------------------------------------------
    def _on_started(self) -> None:
        self._send_initialize()

    def _on_error(self, error) -> None:
        if self.state in (READY, STARTING):
            messages = {
                QProcess.ProcessError.FailedToStart: (
                    f"无法启动 {self.command}，请确认已安装且路径正确"
                ),
                QProcess.ProcessError.Crashed: f"{self.server_key} 进程崩溃",
                QProcess.ProcessError.Timedout: f"{self.server_key} 进程超时",
            }
            self.state = FAILED
            self.failed.emit(messages.get(error, f"{self.server_key} 进程错误：{error}"))

    def _on_finished(self, exit_code: int, _exit_status=None) -> None:
        previous = self.state
        self.state = STOPPED
        if previous != STOPPED:
            self.exited.emit(exit_code)
            if previous != READY:
                self.failed.emit(f"{self.server_key} 启动后退出（code={exit_code}）")

    def _read_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput())
        for message in self._framer.feed(data):
            self._dispatch(message)

    def _read_stderr(self) -> None:
        if self._process is None:
            return
        raw = bytes(self._process.readAllStandardError())
        try:
            text = raw.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return
        if text:
            self.logReceived.emit(text)

    # ---- 内部：协议 -------------------------------------------------------
    def _send_initialize(self) -> None:
        root_uri = path_to_uri(self.root_dir)
        params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "lime", "version": "1.0"},
            "rootUri": root_uri,
            "workspaceFolders": [
                {"uri": root_uri, "name": os.path.basename(self.root_dir.rstrip("/\\")) or "lime"}
            ],
            "capabilities": client_completion_capabilities(),
        }
        self._send_request("initialize", "initialize", params)

    def _send_initialized(self) -> None:
        self._notify("initialized", {})
        self.state = READY
        self.initialized.emit()

    def _notify(self, method: str, params: dict) -> None:
        if self._process is None or self.state in (STOPPED, FAILED):
            return
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _send_request(self, kind: str, method: str, params: dict) -> int:
        self._next_id += 1
        req_id = self._next_id
        self._request_kinds[req_id] = kind
        self._write(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        )
        return req_id

    def _reply_error(self, req_id: Any, code: int, message: str) -> None:
        self._write(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            }
        )

    def _write(self, message: dict) -> None:
        if self._process is None:
            return
        self._process.write(encode_message(message))

    def _dispatch(self, message: dict) -> None:
        method = message.get("method")
        if method is not None:
            if "id" in message:
                # 服务器向客户端发请求：lime 暂不实现任何服务端能力
                self._reply_error(message["id"], -32601, f"未实现的方法：{method}")
                return
            self._dispatch_notification(method, message.get("params") or {})
            return

        req_id = message.get("id")
        kind = self._request_kinds.pop(req_id, None)
        if kind is None:
            return
        if "error" in message:
            self.logReceived.emit(f"{self.server_key} 请求失败：{message['error']}")
            return
        result = message.get("result")
        if kind == "initialize":
            self._capture_capabilities(result or {})
            self._send_initialized()
        elif kind == "completion":
            self.completionReceived.emit(int(req_id), parse_completions(result))

    def _capture_capabilities(self, initialize_result: dict) -> None:
        cap = initialize_result.get("capabilities") or {}
        completion = cap.get("completionProvider") or {}
        triggers = completion.get("triggerCharacters")
        if isinstance(triggers, list) and triggers:
            self.completion_triggers = tuple(str(t) for t in triggers)

    def _dispatch_notification(self, method: str, params: dict) -> None:
        if method == "textDocument/publishDiagnostics":
            uri = str(params.get("uri", ""))
            self.diagnosticsReceived.emit(uri, parse_diagnostics(params))
        elif method in ("window/logMessage", "window/showMessage"):
            message = str(params.get("message", ""))
            if message:
                self.logReceived.emit(f"{self.server_key}: {message}")
        # $/progress、$/cancelRequest、日志等直接忽略
