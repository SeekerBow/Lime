# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""查找替换：可独立测试的纯逻辑 + 作用于编辑器的引擎 + 工具条 UI。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..editor.code_editor import CodeEditor


def compile_pattern(
    pattern: str,
    case_sensitive: bool = False,
    whole_word: bool = False,
    use_regex: bool = False,
) -> re.Pattern:
    """按选项编译查找正则；非法正则抛 :class:`re.error`。"""
    if not use_regex:
        pattern = re.escape(pattern)
    if whole_word:
        pattern = rf"\b(?:{pattern})\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    # DOTALL 让正则模式下 “.” 可跨行；纯文本不受影响
    flags |= re.DOTALL
    return re.compile(pattern, flags)


def find_all(
    text: str,
    pattern: str,
    case_sensitive: bool = False,
    whole_word: bool = False,
    use_regex: bool = False,
) -> list[tuple[int, int]]:
    """返回所有匹配的 ``(起始位置, 结束位置)``。"""
    if not pattern:
        return []
    regex = compile_pattern(pattern, case_sensitive, whole_word, use_regex)
    return [(m.start(), m.end()) for m in regex.finditer(text)]


@dataclass
class SearchOptions:
    case_sensitive: bool = False
    whole_word: bool = False
    use_regex: bool = False

    def flags(self) -> tuple[bool, bool, bool]:
        return (self.case_sensitive, self.whole_word, self.use_regex)


class FindReplaceEngine:
    """在 :class:`CodeEditor` 上执行查找/替换操作。"""

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor
        self._pattern = ""
        self.options = SearchOptions()

    def set_pattern(self, pattern: str) -> None:
        self._pattern = pattern

    def matches(self) -> list[tuple[int, int]]:
        cs, ww, rx = self.options.flags()
        return find_all(self.editor.toPlainText(), self._pattern, cs, ww, rx)

    def count(self) -> int:
        return len(self.matches())

    def find(self, backward: bool = False) -> bool:
        """从当前光标查找下一个/上一个匹配，找到则选中并返回 True。

        纯文本与正则统一走正则实现，以保证向前/向后/回绕语义一致。
        """
        if not self._pattern:
            return False
        cursor = self.editor.textCursor()
        text = self.editor.toPlainText()
        cs, ww, rx = self.options.flags()
        try:
            regex = compile_pattern(self._pattern, cs, ww, rx)
        except re.error:
            return False

        if backward:
            # 从光标位置之前找最近的一个；若光标正停在某个匹配上则跳过它，
            # 前面没有时回绕到最后一个匹配（循环查找）。
            anchor = cursor.position()
            sel_start = cursor.selectionStart() if cursor.hasSelection() else -1
            all_matches = list(regex.finditer(text))
            candidates = [m for m in all_matches if m.start() < anchor]
            if candidates and candidates[-1].start() == sel_start:
                candidates.pop()
            match = candidates[-1] if candidates else (
                all_matches[-1] if all_matches else None
            )
        else:
            pos = cursor.position()
            match = regex.search(text, pos)
            if match is None and pos > 0:
                # 回绕到开头，但不能把当前位置之后刚找过的匹配再找一遍
                wrapped = regex.search(text, 0)
                if wrapped is not None and wrapped.start() < pos:
                    match = wrapped
                else:
                    match = None
        if match is None:
            return False
        new_cursor = self.editor.textCursor()
        new_cursor.setPosition(match.start())
        new_cursor.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(new_cursor)
        return True

    def replace_one(self, replacement: str) -> bool:
        """替换当前选中匹配；未选中匹配时先尝试查找下一个。"""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return self.find() and self.replace_one(replacement)
        cs, ww, rx = self.options.flags()
        regex = compile_pattern(self._pattern, cs, ww, rx)
        selected = cursor.selectedText()
        if regex.fullmatch(selected):
            cursor.insertText(replacement)
            return True
        # 选中的不是目标匹配，先找下一个
        return self.find() and self.replace_one(replacement)

    def replace_all(self, replacement: str) -> int:
        """替换全部匹配，返回替换数量。"""
        cs, ww, rx = self.options.flags()
        text = self.editor.toPlainText()
        try:
            regex = compile_pattern(self._pattern, cs, ww, rx)
            # replacement 中允许使用 \1、\g<name> 等反向引用
            new_text, count = regex.subn(replacement, text)
        except re.error:
            return 0
        if count:
            cursor = self.editor.textCursor()
            cursor.beginEditBlock()
            self.editor.setPlainText(new_text)
            cursor.endEditBlock()
        return count


class FindReplaceBar(QWidget):
    """查找替换工具条（默认隐藏，Ctrl+F / Ctrl+H 唤出）。"""

    closed = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine: FindReplaceEngine | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("查找:"))
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("输入查找内容")
        find_row.addWidget(self.find_input, 1)
        self.case_box = QCheckBox("区分大小写")
        self.word_box = QCheckBox("整词")
        self.regex_box = QCheckBox("正则")
        for box in (self.case_box, self.word_box, self.regex_box):
            find_row.addWidget(box)
        self.btn_prev = QPushButton("上一个")
        self.btn_next = QPushButton("下一个")
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedWidth(26)
        find_row.addWidget(self.btn_prev)
        find_row.addWidget(self.btn_next)
        find_row.addWidget(self.btn_close)
        layout.addLayout(find_row)

        replace_row = QHBoxLayout()
        replace_row.addWidget(QLabel("替换:"))
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("输入替换内容")
        replace_row.addWidget(self.replace_input, 1)
        self.btn_replace = QPushButton("替换")
        self.btn_replace_all = QPushButton("全部替换")
        replace_row.addWidget(self.btn_replace)
        replace_row.addWidget(self.btn_replace_all)
        layout.addLayout(replace_row)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #888;")
        layout.addWidget(self.count_label)

        # 信号
        self.find_input.returnPressed.connect(lambda: self.find_next())
        self.btn_next.clicked.connect(self.find_next)
        self.btn_prev.clicked.connect(self.find_previous)
        self.btn_close.clicked.connect(self.hide_bar)
        self.btn_replace.clicked.connect(self.replace_one)
        self.btn_replace_all.clicked.connect(self.replace_all)
        for box in (self.case_box, self.word_box, self.regex_box):
            box.toggled.connect(self._options_changed)
        self.find_input.textChanged.connect(self._options_changed)

        self.hide()

    # ---- 目标编辑器 ------------------------------------------------------
    def attach(self, editor: CodeEditor | None) -> None:
        self._engine = FindReplaceEngine(editor) if editor is not None else None
        self._sync_options()
        self._update_count()

    def engine(self) -> FindReplaceEngine | None:
        return self._engine

    def show_find(self) -> None:
        self.show()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def show_replace(self) -> None:
        self.show()
        self.replace_input.setFocus()

    def hide_bar(self) -> None:
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
            return
        super().keyPressEvent(event)

    # ---- 操作 ------------------------------------------------------------
    def _sync_options(self) -> None:
        if self._engine is None:
            return
        self._engine.set_pattern(self.find_input.text())
        self._engine.options.case_sensitive = self.case_box.isChecked()
        self._engine.options.whole_word = self.word_box.isChecked()
        self._engine.options.use_regex = self.regex_box.isChecked()

    def _options_changed(self, *_args) -> None:
        self._sync_options()
        self._update_count()

    def _update_count(self) -> None:
        if self._engine is None or not self.find_input.text():
            self.count_label.setText("")
            return
        try:
            count = self._engine.count()
        except re.error as exc:
            self.count_label.setText(f"正则无效：{exc}")
            return
        self.count_label.setText(f"匹配 {count} 处")

    def find_next(self) -> bool:
        return self._do_find(False)

    def find_previous(self) -> bool:
        return self._do_find(True)

    def _do_find(self, backward: bool) -> bool:
        if self._engine is None:
            return False
        self._sync_options()
        try:
            found = self._engine.find(backward)
        except re.error as exc:
            self.message.emit(f"正则无效：{exc}")
            return False
        if not found:
            self.count_label.setText("没有匹配项")
        return found

    def replace_one(self) -> None:
        if self._engine is None:
            return
        self._sync_options()
        self._engine.replace_one(self.replace_input.text())
        self._update_count()

    def replace_all(self) -> int:
        if self._engine is None:
            return 0
        self._sync_options()
        try:
            count = self._engine.replace_all(self.replace_input.text())
        except re.error as exc:
            self.message.emit(f"正则无效：{exc}")
            return 0
        self.count_label.setText(f"已替换 {count} 处")
        return count
