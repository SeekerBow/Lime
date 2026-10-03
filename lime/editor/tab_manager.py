# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""多标签编辑管理：新建/打开/保存/关闭文档。"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTabWidget, QWidget

from ..core.settings import Settings
from .code_editor import CodeEditor
from .highlighter import PygmentsHighlighter, lexer_for_filename


def _normalize(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class TabManager(QTabWidget):
    """承载多个 :class:`CodeEditor` 的标签容器。"""

    #: 当前标签文件路径变化（str 或 None）
    current_file_changed = pyqtSignal(object)
    #: 当前编辑器修改状态变化
    modification_changed = pyqtSignal(bool)
    #: 文件被打开/另存，可用于写入最近文件
    file_tracked = pyqtSignal(str)
    #: 新编辑器创建（可用于挂接补全控制器等）
    editor_created = pyqtSignal(object)
    #: 文件被打开（磁盘文件载入新标签）
    file_opened = pyqtSignal(str)
    #: 文件被保存：(新路径, 旧路径或 None)
    file_saved = pyqtSignal(str, object)
    #: 带路径的标签被关闭
    file_closed = pyqtSignal(str)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._paths: dict[CodeEditor, Optional[str]] = {}
        self._untitled_counter = 0

        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.currentChanged.connect(self._on_current_changed)

    # ---- 创建/配置编辑器 --------------------------------------------------
    def _create_editor(self) -> CodeEditor:
        editor = CodeEditor()
        editor.apply_settings(self.settings)
        highlighter = PygmentsHighlighter(
            editor.document(), style_name=self.settings.highlight_style
        )
        editor.highlighter = highlighter
        self._apply_editor_theme(editor)
        editor.modificationChanged.connect(lambda _=None, e=editor: self._on_modified(e))
        self._paths[editor] = None
        self.editor_created.emit(editor)
        return editor

    def _apply_editor_theme(self, editor: CodeEditor) -> None:
        if editor.highlighter is None:
            return
        editor.apply_color_scheme(
            editor.highlighter.background_color(),
            editor.highlighter.foreground_color(),
        )

    def refresh_settings(self) -> None:
        """设置变化后刷新所有编辑器与高亮样式。"""
        for editor in self._paths:
            editor.apply_settings(self.settings)
            if editor.highlighter is not None:
                editor.highlighter.set_style(self.settings.highlight_style)
                self._apply_editor_theme(editor)

    # ---- 属性 ------------------------------------------------------------
    def current_editor(self) -> Optional[CodeEditor]:
        return self.currentWidget()  # type: ignore[return-value]

    def current_path(self) -> Optional[str]:
        editor = self.current_editor()
        return self._paths.get(editor) if editor is not None else None

    def path_for(self, editor: CodeEditor) -> Optional[str]:
        return self._paths.get(editor)

    def editor_for_path(self, path: str) -> Optional[CodeEditor]:
        for editor, editor_path in self._paths.items():
            if editor_path and _normalize(editor_path) == _normalize(path):
                return editor
        return None

    def is_modified(self, editor: CodeEditor | None = None) -> bool:
        editor = editor or self.current_editor()
        return editor.document().isModified() if editor is not None else False

    # ---- 新建/打开 --------------------------------------------------------
    def new_document(self) -> CodeEditor:
        editor = self._create_editor()
        self._untitled_counter += 1
        title = f"未命名-{self._untitled_counter}"
        index = self.addTab(editor, title)
        self.setCurrentIndex(index)
        editor.document().setModified(False)
        return editor

    def open_file(self, path: str) -> Optional[CodeEditor]:
        """打开文件；已打开则切换到对应标签。"""
        path = os.path.abspath(path)
        for editor, editor_path in self._paths.items():
            if editor_path and _normalize(editor_path) == _normalize(path):
                self.setCurrentWidget(editor)
                return editor

        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            QMessageBox.critical(self, "打开失败", f"无法读取文件：\n{exc}")
            return None

        text = raw.decode("utf-8", errors="replace")
        editor = self._create_editor()
        editor.setPlainText(text)
        if editor.highlighter is not None:
            editor.highlighter.set_lexer(lexer_for_filename(path))
        self._paths[editor] = path
        index = self.addTab(editor, os.path.basename(path))
        self.setTabToolTip(index, path)
        self.setCurrentIndex(index)
        editor.document().setModified(False)
        self.settings.last_dir = os.path.dirname(path)
        self.file_tracked.emit(path)
        self.file_opened.emit(path)
        self._on_current_changed()
        return editor

    def open_paths(self, paths) -> list[CodeEditor]:
        editors: list[CodeEditor] = []
        for path in paths:
            editor = self.open_file(path)
            if editor is not None:
                editors.append(editor)
        return editors

    # ---- 保存 ------------------------------------------------------------
    def save_current(self) -> bool:
        editor = self.current_editor()
        if editor is None:
            return False
        path = self._paths.get(editor)
        if path is None:
            return self.save_current_as()
        return self._save_to_path(editor, path)

    def save_current_as(self) -> bool:
        editor = self.current_editor()
        if editor is None:
            return False
        start_dir = self._starting_dir(editor)
        path, _ = QFileDialog.getSaveFileName(self, "另存为", start_dir)
        if not path:
            return False
        return self._save_to_path(editor, path)

    def _save_to_path(self, editor: CodeEditor, path: str) -> bool:
        old_path = self._paths.get(editor)
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(editor.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入文件：\n{exc}")
            return False
        self._paths[editor] = path
        editor.document().setModified(False)
        index = self.indexOf(editor)
        if index >= 0:
            self.setTabText(index, os.path.basename(path))
            self.setTabToolTip(index, path)
        if editor.highlighter is not None:
            editor.highlighter.set_lexer(lexer_for_filename(path))
            self._apply_editor_theme(editor)
        self.settings.last_dir = os.path.dirname(path)
        self.file_tracked.emit(path)
        self.file_saved.emit(path, old_path)
        return True

    def _starting_dir(self, editor: CodeEditor) -> str:
        path = self._paths.get(editor)
        if path:
            return path
        return self.settings.last_dir or os.path.expanduser("~")

    # ---- 关闭 ------------------------------------------------------------
    def close_tab(self, index: int) -> bool:
        editor = self.widget(index)
        if editor is None:
            return True
        if not self._confirm_discard(editor):
            return False
        path = self._paths.pop(editor, None)
        self.removeTab(index)
        editor.deleteLater()
        if path:
            self.file_closed.emit(path)
        return True

    def close_current(self) -> bool:
        return self.close_tab(self.currentIndex())

    def confirm_close_all(self) -> bool:
        """窗口关闭前调用，逐个确认未保存文档；全部可丢弃才返回 True。"""
        for editor in list(self._paths):
            if editor.document().isModified() and not self._confirm_discard(editor):
                return False
        return True

    def _confirm_discard(self, editor: CodeEditor) -> bool:
        if not editor.document().isModified():
            return True
        name = self._paths.get(editor) or self.tabText(self.indexOf(editor))
        answer = QMessageBox.question(
            self,
            "保存更改",
            f"文件 “{os.path.basename(str(name))}” 已修改，是否保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        path = self._paths.get(editor)
        if path is not None:
            return self._save_to_path(editor, path)
        return self.save_current_as()

    # ---- 内部槽 ----------------------------------------------------------
    def _on_modified(self, editor: CodeEditor) -> None:
        if editor is not self.current_editor():
            # 仍需刷新该标签的脏圆点
            self._refresh_label(editor)
            return
        self._refresh_label(editor)
        self.modification_changed.emit(editor.document().isModified())

    def _refresh_label(self, editor: CodeEditor) -> None:
        index = self.indexOf(editor)
        if index < 0:
            return
        path = self._paths.get(editor)
        current_title = self.tabText(index)
        if path:
            base = os.path.basename(path)
        else:
            # 去掉脏标记前缀，保留“未命名-N”
            base = current_title[2:] if current_title.startswith("• ") else current_title
        if editor.document().isModified():
            base = f"• {base}"
        self.setTabText(index, base)

    def _on_current_changed(self, *_args) -> None:
        editor = self.current_editor()
        path = self._paths.get(editor) if editor is not None else None
        self.current_file_changed.emit(path)
        self.modification_changed.emit(
            editor.document().isModified() if editor is not None else False
        )
