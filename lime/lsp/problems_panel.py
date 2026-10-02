"""实时诊断（Problems）面板：列出所有打开文件的 LSP 诊断，双击跳转。"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..editor.code_editor import SEVERITY_COLORS

#: 严重级别 -> 文本标记
SEVERITY_MARK = {1: "✖", 2: "▲", 3: "ℹ", 4: "…"}


class ProblemsPanel(QWidget):
    #: 请求跳转到 ``(path, 0 基行, 0 基列)``
    open_requested = pyqtSignal(str, int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: dict[str, list] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.summary = QLabel("暂无问题")
        layout.addWidget(self.summary)

        self.list_widget = QListWidget()
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.list_widget.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self.list_widget, 1)

    # ---- 数据 ------------------------------------------------------------
    def update_file(self, path: str, diagnostics: list) -> int:
        """更新单个文件的诊断，返回当前问题总数。"""
        normalized = os.path.normcase(os.path.normpath(path))
        if diagnostics:
            self._entries[normalized] = list(diagnostics)
        else:
            self._entries.pop(normalized, None)
        self._rebuild()
        return self.count()

    def count(self) -> int:
        return sum(len(items) for items in self._entries.values())

    def entries(self) -> list[tuple[str, object]]:
        result: list[tuple[str, object]] = []
        for normalized, items in self._entries.items():
            for diag in items:
                result.append((normalized, diag))
        return result

    # ---- 渲染 ------------------------------------------------------------
    def _rebuild(self) -> None:
        self.list_widget.clear()
        ordered = sorted(
            self.entries(),
            key=lambda pair: (pair[1].severity, pair[0], pair[1].start_line, pair[1].start_char),
        )
        error_count = sum(1 for _p, d in ordered if d.severity == 1)
        warn_count = sum(1 for _p, d in ordered if d.severity == 2)

        for path, diag in ordered:
            mark = SEVERITY_MARK.get(diag.severity, "✖")
            source = f"[{diag.source}] " if diag.source else ""
            text = (
                f"{mark} {diag.severity_label()}: {source}{diag.message}    "
                f"({os.path.basename(path)}:{diag.start_line + 1}:{diag.start_char + 1})"
            )
            item = QListWidgetItem(text)
            item.setForeground(QColor(SEVERITY_COLORS.get(diag.severity, "#f14c4c")))
            item.setData(Qt.ItemDataRole.UserRole, (path, diag.start_line, diag.start_char))
            self.list_widget.addItem(item)

        if not ordered:
            self.summary.setText("暂无问题")
        else:
            parts = []
            if error_count:
                parts.append(f"{error_count} 个错误")
            if warn_count:
                parts.append(f"{warn_count} 个警告")
            other = len(ordered) - error_count - warn_count
            if other > 0:
                parts.append(f"{other} 条提示")
            self.summary.setText("，".join(parts))

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            path, line, char = data
            self.open_requested.emit(path, line, char)
