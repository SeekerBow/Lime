# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pygments 与 Qt 文档模型之间的桥接层。

:class:`PygmentsHighlighter` 把 Pygments lexer 的 token 流着色到
:class:`QTextDocument`。

与常见的“每行单独词法分析”实现不同，这里始终对**整份文档**做一次
词法分析，再把可能跨行的 token（C/C++/Java 的 ``/* ... */`` 多行注释、
Python 三引号字符串、行延续宏等）拆分回各个文本块。这样跨行结构在
编辑过程中也能持续正确着色；块状态（block state）随打开的跨行
token 栈变化，Qt 会据此自动重新高亮后续块。
"""

from __future__ import annotations

import bisect
import os
from typing import Optional

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from pygments.lexers import get_lexer_for_filename
from pygments.style import Style
from pygments.token import Token
from pygments.util import ClassNotFound

from .themes import AVAILABLE_STYLE_NAMES, get_style

#: 可选的 Pygments 样式名列表（内置 + lime 自定义）
AVAILABLE_STYLES: tuple[str, ...] = AVAILABLE_STYLE_NAMES

_NO_FORMAT = object()

#: 为未闭合的跨行结构追加的哨兵：让文档末尾未闭合的 ``/* ...``
#: 也能按注释着色。哨兵产生的 token 位于真实文档范围之外，会被丢弃。
_EOF_SENTINEL = "\n*/"


def lexer_for_filename(path: str):
    """根据文件名返回 Pygments lexer，无法识别时返回 ``None``。"""
    try:
        return get_lexer_for_filename(os.path.basename(path))
    except ClassNotFound:
        return None


def build_format(spec: str) -> QTextCharFormat:
    """把 Pygments 样式描述串（如 ``"bold italic #ff0000"``）转成 Qt 格式。"""
    fmt = QTextCharFormat()
    for part in spec.split():
        if part.startswith("#") and len(part) in (4, 7):
            fmt.setForeground(QColor(part))
        elif part == "bold":
            fmt.setFontWeight(QFont.Weight.Bold)
        elif part == "italic":
            fmt.setFontItalic(True)
        elif part in ("underline", "underline:"):
            fmt.setFontUnderline(True)
    return fmt


class PygmentsHighlighter(QSyntaxHighlighter):
    """把 Pygments token 流着色到 :class:`QTextDocument`。"""

    def __init__(self, document, lexer=None, style_name: str = "default") -> None:
        super().__init__(document)
        self._lexer = lexer
        self._style: Optional[Style] = None
        self._formats: dict = {}
        # 整份文档的着色缓存，随文档 revision 失效
        self._cache_revision: int = -1
        self._entries: dict[int, list[tuple[int, object, str]]] = {}
        self._states: dict[int, int] = {}
        self.set_style(style_name)
        if lexer is not None:
            self.set_lexer(lexer)

    # ---- 配置 -----------------------------------------------------------
    def set_lexer(self, lexer) -> None:
        self._lexer = lexer
        self._invalidate()
        self.rehighlight()

    def lexer(self):
        return self._lexer

    def set_style(self, style_name: str) -> None:
        self._style_name = style_name
        self._style = get_style(style_name)
        self._formats = {}
        # Token 自身的默认前景色
        base_spec = self._style.styles.get(Token, "")
        self._formats[Token] = build_format(base_spec) if base_spec else _NO_FORMAT
        self._invalidate()
        self.rehighlight()

    @property
    def style_name(self) -> str:
        return self._style_name

    def background_color(self) -> str:
        """样式定义的背景色（十六进制），用于编辑器配色。"""
        return self._style.background_color or "#ffffff"

    def foreground_color(self) -> str:
        return getattr(self._style, "styles", {}).get(Token) and _first_color(
            self._style.styles[Token]
        ) or "#000000"

    # ---- 着色 -----------------------------------------------------------
    def _resolve_format(self, token):
        """沿 token 父链向上查找最近的样式定义，结果缓存。"""
        cached = self._formats.get(token)
        if cached is not None:
            return None if cached is _NO_FORMAT else cached

        current = token
        spec = None
        while current is not None:
            current_spec = self._style.styles.get(current)
            if current_spec:
                spec = current_spec
                break
            if current == Token:
                break
            current = current.parent

        result = build_format(spec) if spec else _NO_FORMAT
        self._formats[token] = result
        return None if result is _NO_FORMAT else result

    def _invalidate(self) -> None:
        self._cache_revision = -1
        self._entries = {}
        self._states = {}

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt API)
        if self._lexer is None:
            return
        document = self.document()
        if document is None:
            return
        if document.revision() != self._cache_revision:
            self._rebuild_cache(document)
            self._cache_revision = document.revision()

        block_no = self.currentBlock().blockNumber()
        for column, token, value in self._entries.get(block_no, ()):  # noqa: B007
            fmt = self._resolve_format(token)
            if fmt is not None and value:
                self.setFormat(column, len(value), fmt)
        # 块末尾所处的跨行状态；与上次不同时 Qt 会自动重高亮后续块
        self.setCurrentBlockState(self._states.get(block_no, 0))

    # ---- 整文档缓存 ------------------------------------------------------
    def _rebuild_cache(self, document) -> None:
        """对整份文档词法分析一次，产出每块的 token 片段与块状态。"""
        block_texts: list[str] = []
        block = document.firstBlock()
        while block.isValid():
            block_texts.append(block.text())
            block = block.next()

        line_starts: list[int] = []
        offset = 0
        for text in block_texts:
            line_starts.append(offset)
            offset += len(text) + 1  # +1 为块分隔符 '\n'

        full_text = "\n".join(block_texts)
        entries: dict[int, list[tuple[int, object, str]]] = {
            i: [] for i in range(len(block_texts))
        }
        # (行号, 是否压栈, token) —— 按文档顺序记录跨行 token 的开/合
        span_events: list[tuple[int, int, object]] = []

        try:
            tokens = list(
                self._lexer.get_tokens_unprocessed(full_text + _EOF_SENTINEL)
            )
        except Exception:
            # 任何 lexer 异常都不应让编辑器崩溃：保持无着色
            self._entries = entries
            self._states = {}
            return

        block_count = len(block_texts)
        for index, token, value in tokens:
            if "\n" not in value:
                self._append_piece(
                    entries, line_starts, block_count, index, token, value
                )
                continue

            parts = value.split("\n")
            pos = index
            first_content_line: Optional[int] = None
            last_content_line: Optional[int] = None
            for part in parts:
                line_no = bisect.bisect_right(line_starts, pos) - 1
                if part:
                    if 0 <= line_no < block_count:
                        column = pos - line_starts[line_no]
                        entries[line_no].append((column, token, part))
                    if first_content_line is None:
                        first_content_line = line_no
                    last_content_line = line_no
                pos += len(part) + 1  # 跳过片段与一个 '\n'

            # 只有真正跨越了两行内容才算跨行结构（过滤纯换行/末尾换行）
            if (
                first_content_line is not None
                and last_content_line is not None
                and last_content_line > first_content_line
                and 0 <= first_content_line < block_count
            ):
                span_events.append((first_content_line, 1, token))
                close_line = min(last_content_line, block_count - 1)
                span_events.append((close_line, 0, token))

        self._entries = entries
        self._states = self._build_states(span_events, block_count)

    @staticmethod
    def _append_piece(
        entries, line_starts, block_count, index, token, value
    ) -> None:
        line_no = bisect.bisect_right(line_starts, index) - 1
        if 0 <= line_no < block_count:
            column = index - line_starts[line_no]
            entries[line_no].append((column, token, value))

    @staticmethod
    def _build_states(
        span_events: list[tuple[int, int, object]], block_count: int
    ) -> dict[int, int]:
        """根据跨行 token 的压/弹事件计算每块末尾的状态码。"""
        states: dict[int, int] = {}
        open_stack: list[object] = []
        events_by_line: dict[int, list[tuple[int, object]]] = {}
        for line_no, push, token in span_events:
            events_by_line.setdefault(line_no, []).append((push, token))

        for line_no in range(block_count):
            for push, token in events_by_line.get(line_no, ()):
                if push:
                    open_stack.append(token)
                elif token in open_stack:
                    # 从栈顶向下移除最近的同类 token，容忍嵌套
                    for depth in range(len(open_stack) - 1, -1, -1):
                        if open_stack[depth] == token:
                            del open_stack[depth]
                            break
            states[line_no] = _state_id(open_stack)
        return states


def _state_id(stack: list[object]) -> int:
    """把跨行 token 栈压成稳定的 31 位非负整数状态码。"""
    code = 0
    for token in stack:
        code = (code * 1000003) ^ (hash(token) & 0xFFFF)
    return code & 0x7FFFFFFF


def _first_color(spec: str) -> str:
    for part in spec.split():
        if part.startswith("#"):
            return part
    return "#000000"
