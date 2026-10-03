# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""设置对话框：编辑可持久化的用户偏好。"""

from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..core.settings import Settings
from ..editor.highlighter import AVAILABLE_STYLES


class SettingsDialog(QDialog):
    """表单式偏好设置，确定时写回 :class:`Settings`。"""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.font_family))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 36)
        self.font_size.setValue(settings.font_size)
        self.tab_width = QSpinBox()
        self.tab_width.setRange(1, 16)
        self.tab_width.setValue(settings.tab_width)
        self.spaces_box = QCheckBox("用空格替代 Tab")
        self.spaces_box.setChecked(settings.spaces_instead_of_tabs)
        self.line_numbers_box = QCheckBox("显示行号")
        self.line_numbers_box.setChecked(settings.line_numbers)
        self.word_wrap_box = QCheckBox("自动换行")
        self.word_wrap_box.setChecked(settings.word_wrap)

        self.style_combo = QComboBox()
        self.style_combo.addItems(AVAILABLE_STYLES)
        idx = self.style_combo.findText(settings.highlight_style)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)

        self.host_edit = QLineEdit(settings.ollama_host)
        self.host_edit.setPlaceholderText("http://127.0.0.1:11434")
        self.model_edit = QLineEdit(settings.ollama_model)
        self.model_edit.setPlaceholderText("留空则在侧边栏刷新选择")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(settings.ollama_timeout)
        self.shell_edit = QLineEdit(settings.terminal_shell)
        self.shell_edit.setPlaceholderText("留空使用系统默认（cmd/bash）")

        self.lsp_box = QCheckBox("启用实时代码解析与智能补全（需要 clangd）")
        self.lsp_box.setChecked(settings.lsp_enabled)
        self.clangd_edit = QLineEdit(settings.clangd_command)
        self.clangd_edit.setPlaceholderText("clangd（或 clangd.exe 的完整路径）")

        form.addRow("字体", self.font_combo)
        form.addRow("字号", self.font_size)
        form.addRow("Tab 宽度", self.tab_width)
        form.addRow("", self.spaces_box)
        form.addRow("", self.line_numbers_box)
        form.addRow("", self.word_wrap_box)
        form.addRow("高亮样式", self.style_combo)
        form.addRow("Ollama 地址", self.host_edit)
        form.addRow("Ollama 模型", self.model_edit)
        form.addRow("AI 超时", self.timeout_spin)
        form.addRow("终端 Shell", self.shell_edit)
        form.addRow("", self.lsp_box)
        form.addRow("clangd 路径", self.clangd_edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self) -> None:  # noqa: N802 (Qt API)
        s = self.settings
        s.font_family = self.font_combo.currentFont().family()
        s.font_size = self.font_size.value()
        s.tab_width = self.tab_width.value()
        s.spaces_instead_of_tabs = self.spaces_box.isChecked()
        s.line_numbers = self.line_numbers_box.isChecked()
        s.word_wrap = self.word_wrap_box.isChecked()
        s.highlight_style = self.style_combo.currentText()
        s.ollama_host = self.host_edit.text().strip()
        s.ollama_model = self.model_edit.text().strip()
        s.ollama_timeout = self.timeout_spin.value()
        s.terminal_shell = self.shell_edit.text().strip()
        s.lsp_enabled = self.lsp_box.isChecked()
        s.clangd_command = self.clangd_edit.text().strip() or "clangd"
        s.sync()
        super().accept()
