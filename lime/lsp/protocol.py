# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""LSP 协议的纯逻辑部分：JSON-RPC 帧、URI 转换、数据结构、服务器注册。

不依赖 Qt、不启动进程，可完全离线单测。
参考：https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, unquote, urlparse

# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
SEVERITY_LABELS = {1: "错误", 2: "警告", 3: "信息", 4: "提示"}


@dataclass
class Diagnostic:
    """``textDocument/publishDiagnostics`` 中的一条诊断。"""

    start_line: int
    start_char: int
    end_line: int
    end_char: int
    severity: int = 1
    message: str = ""
    source: str = ""

    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, "错误")

    @staticmethod
    def from_lsp(item: dict) -> "Diagnostic":
        rng = item.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or start
        return Diagnostic(
            start_line=int(start.get("line", 0)),
            start_char=int(start.get("character", 0)),
            end_line=int(end.get("line", start.get("line", 0))),
            end_char=int(end.get("character", start.get("character", 0))),
            severity=int(item.get("severity", 1)),
            message=str(item.get("message", "")),
            source=str(item.get("source", "") or ""),
        )


@dataclass
class TextEdit:
    start_line: int
    start_char: int
    end_line: int
    end_char: int
    new_text: str

    @staticmethod
    def from_lsp(edit: dict) -> "TextEdit":
        rng = edit.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or start
        return TextEdit(
            int(start.get("line", 0)),
            int(start.get("character", 0)),
            int(end.get("line", 0)),
            int(end.get("character", 0)),
            str(edit.get("newText", "")),
        )


@dataclass
class CompletionItem:
    """补全候选项（已抹平 CompletionItem / CompletionList 差异）。"""

    label: str
    insert_text: str = ""
    detail: str = ""
    kind: int = 0
    text_edit: Optional[TextEdit] = None

    @property
    def insert_value(self) -> str:
        return self.text_edit.new_text if self.text_edit else (self.insert_text or self.label)

    @staticmethod
    def from_lsp(item: dict) -> "CompletionItem":
        text_edit = None
        raw_edit = item.get("textEdit")
        if isinstance(raw_edit, dict):
            if "range" in raw_edit:  # TextEdit
                text_edit = TextEdit.from_lsp(raw_edit)
            elif "insert" in raw_edit:  # InsertReplaceEdit：用 insert 范围
                text_edit = TextEdit.from_lsp(
                    {"range": raw_edit.get("insert"), "newText": raw_edit.get("newText", "")}
                )
        return CompletionItem(
            label=str(item.get("label", "")),
            insert_text=str(item.get("insertText", "") or ""),
            detail=str(item.get("detail", "") or ""),
            kind=int(item.get("kind", 0) or 0),
            text_edit=text_edit,
        )


def parse_diagnostics(payload: dict) -> list[Diagnostic]:
    items = payload.get("diagnostics") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [Diagnostic.from_lsp(i) for i in items if isinstance(i, dict)]


def parse_completions(result) -> list[CompletionItem]:
    """completion 请求结果可能是列表或 ``{"items": [...]}``。"""
    if result is None:
        return []
    if isinstance(result, dict):
        raw_items = result.get("items", [])
    elif isinstance(result, list):
        raw_items = result
    else:
        return []
    return [CompletionItem.from_lsp(i) for i in raw_items if isinstance(i, dict)]


# --------------------------------------------------------------------------
# URI 转换（Windows 盘符也要正确处理）
# --------------------------------------------------------------------------
def path_to_uri(path: str) -> str:
    path = os.path.abspath(path)
    if os.name == "nt" or (len(path) > 1 and path[1] == ":"):
        # file:///E:/dir/x.cpp（冒号保留，与 VSCode/clangd 一致）
        return "file:///" + quote(path.replace("\\", "/"), safe=":/")
    return "file://" + quote(path)


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if os.name == "nt" or re.match(r"^/[A-Za-z]:", path):
        # file:///E:/dir/x.cpp -> E:\dir\x.cpp
        path = path.lstrip("/").replace("/", "\\")
    return os.path.normpath(path)


# --------------------------------------------------------------------------
# 语言 / 服务器注册
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ServerSpec:
    key: str
    display_name: str
    extensions: frozenset[str]
    languages: frozenset[str]
    args: tuple[str, ...] = ()


#: clangd：C/C++/Objective-C；.h 默认按 C++ 处理（clangd 的默认启发）
CLANGD = ServerSpec(
    key="clangd",
    display_name="clangd",
    extensions=frozenset({".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".m", ".mm"}),
    languages=frozenset({"c", "cpp", "objective-c", "objective-cpp"}),
    args=(
        "--background-index",
        "--clang-tidy",
        "--header-insertion=never",
        "--completion-style=detailed",
        "--log=error",
    ),
)

SERVERS: tuple[ServerSpec, ...] = (CLANGD,)

_EXT_TO_LANG = {
    ".c": "c",
    ".h": "cpp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".m": "objective-c",
    ".mm": "objective-cpp",
}


def language_id_for_path(path: str) -> Optional[str]:
    return _EXT_TO_LANG.get(os.path.splitext(path)[1].lower())


def server_for_path(path: str) -> Optional[ServerSpec]:
    ext = os.path.splitext(path)[1].lower()
    for spec in SERVERS:
        if ext in spec.extensions:
            return spec
    return None


# --------------------------------------------------------------------------
# JSON-RPC over stdio 分帧
# --------------------------------------------------------------------------
def encode_message(message: dict) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


class MessageFramer:
    """增量累积字节流并切出完整 JSON-RPC 消息。

    用法::

        for msg in framer.feed(raw_bytes):
            ...
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[dict]:
        self._buffer.extend(data)
        messages: list[dict] = []
        while True:
            header_end = self._buffer.find(b"\r\n\r\n")
            if header_end < 0:
                break
            header_block = bytes(self._buffer[:header_end])
            length = None
            for line in header_block.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    try:
                        length = int(line.split(b":", 1)[1].strip())
                    except ValueError:
                        length = None
            if length is None:
                # 不是合法帧头，丢弃到下一个分隔符避免死循环
                del self._buffer[: header_end + 4]
                continue
            body_start = header_end + 4
            body_end = body_start + length
            if len(self._buffer) < body_end:
                break  # 消息体未到齐，等待后续数据
            body = bytes(self._buffer[body_start:body_end])
            del self._buffer[:body_end]
            try:
                messages.append(json.loads(body.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return messages


def client_completion_capabilities() -> dict:
    """lime 声明的客户端能力（补全相关）。"""
    return {
        "textDocument": {
            "synchronization": {"didSave": True},
            "completion": {
                "completionItem": {"snippetSupport": False, "documentationFormat": []},
                "contextSupport": False,
            },
            "publishDiagnostics": {"relatedInformation": True},
        },
        "workspace": {"workspaceFolders": True},
    }
