# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""代码编辑器控件：行号栏、当前行高亮、可配置缩进、诊断标记。"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

from ..core.settings import Settings
from .themes import is_dark, mix_color

#: LSP 诊断严重级别 -> 波浪线颜色（VSCode 系配色，深浅底均可读）
SEVERITY_COLORS = {
    1: "#f14c4c",  # error
    2: "#cca700",  # warning
    3: "#2f81f7",  # info
    4: "#8c8c8c",  # hint
}


class LineNumberArea(QWidget):
    """行号绘制区域，宽度由编辑器决定。"""

    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """带行号与缩进支持的代码编辑器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.highlighter = None  # 由外部（TabManager）挂接
        self.completion_controller = None  # 由外部（MainWindow）挂接

        self._tab_width = 4
        self._spaces_instead_of_tabs = True
        self._line_numbers_visible = True

        # 主题配色（默认浅色，与历史外观一致）
        self._theme_dark = False
        self._gutter_bg = "#f0f0f0"
        self._gutter_fg = "#888888"
        self._current_line_color = QColor(232, 232, 235, 90)

        # LSP 诊断（lime.lsp.protocol.Diagnostic 等鸭子类型对象列表）
        self._diagnostics: list = []
        self._last_diag_jump: tuple[int, int] | None = None

        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self._update_margin_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._update_margin_width()
        self._highlight_current_line()

    # ---- 配置 -----------------------------------------------------------
    def apply_settings(self, settings: Settings) -> None:
        font = QFont(settings.font_family, settings.font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self._tab_width = max(1, settings.tab_width)
        self._spaces_instead_of_tabs = settings.spaces_instead_of_tabs
        self._apply_tab_stops()
        self.set_line_numbers_visible(settings.line_numbers)
        self.set_word_wrap(settings.word_wrap)
        # 让行高随字体刷新
        self._update_margin_width()

    def _apply_tab_stops(self) -> None:
        """让物理制表符与插入空格都按当前 Tab 宽度（默认 4）显示。"""
        step = self.fontMetrics().horizontalAdvance(" ") * self._tab_width
        self.setTabStopDistance(max(1.0, float(step)))

    def set_tab_width(self, width: int) -> None:
        self._tab_width = max(1, int(width))
        self._apply_tab_stops()

    def tab_width(self) -> int:
        return self._tab_width

    def set_spaces_instead_of_tabs(self, value: bool) -> None:
        self._spaces_instead_of_tabs = bool(value)

    def spaces_instead_of_tabs(self) -> bool:
        return self._spaces_instead_of_tabs

    def set_word_wrap(self, value: bool) -> None:
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if value
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def word_wrap(self) -> bool:
        return self.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._line_numbers_visible = bool(visible)
        self.line_number_area.setVisible(visible)
        self._update_margin_width()

    # ---- 主题配色 --------------------------------------------------------
    def apply_color_scheme(self, background: str, foreground: str) -> None:
        """按高亮样式的背景/前景色刷新编辑器、行号栏、当前行与选中色。"""
        dark = is_dark(background)
        self._theme_dark = dark
        self._gutter_bg = mix_color(background, "#000000" if dark else "#ffffff",
                                    0.12 if dark else 0.04)
        self._gutter_fg = mix_color(foreground, background, 0.45)
        self._current_line_color = QColor(
            255, 255, 255, 36
        ) if dark else QColor(0, 0, 0, 18)

        palette = self.palette()
        bg = QColor(background)
        fg = QColor(foreground)
        palette.setColor(QPalette.ColorRole.Base, bg)
        palette.setColor(QPalette.ColorRole.AlternateBase, bg)
        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.Text, fg)
        palette.setColor(QPalette.ColorRole.WindowText, fg)
        palette.setColor(QPalette.ColorRole.Highlight, QColor(mix_color(background, foreground, 0.28)))
        palette.setColor(QPalette.ColorRole.HighlightedText, fg)
        self.setPalette(palette)
        # viewport 是独立的子控件，且全局样式表重抛光时 QStyleSheetStyle
        # 会用缓存的旧 palette 覆盖它，必须显式设置才能随主题切换
        self.viewport().setPalette(palette)
        self.line_number_area.setPalette(palette)
        self.line_number_area.update()
        self._highlight_current_line()

    def line_numbers_visible(self) -> bool:
        return self._line_numbers_visible

    # ---- 行号栏 ----------------------------------------------------------
    def line_number_area_width(self) -> int:
        if not self._line_numbers_visible:
            return 0
        digits = max(2, len(str(max(1, self.blockCount()))))
        space = 8 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def _update_margin_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin_width()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event) -> None:
        if not self._line_numbers_visible:
            return
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self._gutter_bg))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(self._gutter_fg))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    # ---- 当前行高亮 + LSP 诊断标记 ---------------------------------------
    def _highlight_current_line(self) -> None:
        selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(self._current_line_color)
            selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)
        selections.extend(self._diagnostic_selections())
        self.setExtraSelections(selections)

    def _diagnostic_selections(self) -> list:
        selections: list = []
        document = self.document()
        for diag in self._diagnostics:
            start_block = document.findBlockByNumber(diag.start_line)
            if not start_block.isValid():
                continue
            end_block = document.findBlockByNumber(diag.end_line)
            if not end_block.isValid():
                end_block = start_block
            start = start_block.position() + min(
                diag.start_char, len(start_block.text())
            )
            end = end_block.position() + min(diag.end_char, len(end_block.text()))
            if end < start + 1:
                end = min(start + 1, document.characterCount() - 1)

            cursor = QTextCursor(document)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            color = QColor(SEVERITY_COLORS.get(diag.severity, SEVERITY_COLORS[1]))
            fmt = selection.format
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(color)
            selections.append(selection)
        return selections

    def set_diagnostics(self, diagnostics: list) -> None:
        """设置当前文件的诊断列表并刷新波浪线。"""
        self._diagnostics = list(diagnostics)
        self._last_diag_jump = None
        self._highlight_current_line()

    def diagnostics(self) -> list:
        return list(self._diagnostics)

    def diagnostic_at(self, line: int, column: int):
        """返回覆盖 ``(0 基行, 0 基列)`` 的最严重诊断，无则 ``None``。"""
        best = None
        best_severity = 99
        for diag in self._diagnostics:
            if not (diag.start_line <= line <= diag.end_line):
                continue
            if line == diag.start_line and column < diag.start_char:
                continue
            if line == diag.end_line and column > diag.end_char:
                continue
            if diag.severity < best_severity:
                best, best_severity = diag, diag.severity
        return best

    def goto_next_diagnostic(self, forward: bool = True):
        """跳到相对光标的下一条（或上一条）诊断，返回该诊断；无则 ``None``。"""
        if not self._diagnostics:
            return None
        ordered = sorted(self._diagnostics, key=lambda d: (d.start_line, d.start_char))
        cursor_line, cursor_col = self.textCursor().blockNumber(), self.textCursor().positionInBlock()
        pos = (cursor_line, cursor_col)
        target = None
        if forward:
            for diag in ordered:
                start = (diag.start_line, diag.start_char)
                end = (diag.end_line, diag.end_char)
                if start < pos <= end:
                    # 光标停在某诊断内部：跳过它，找其后第一条
                    for later in ordered:
                        if (later.start_line, later.start_char) > end:
                            target = later
                            break
                    target = target or ordered[0]
                    break
                if start >= pos and start != self._last_diag_jump:
                    target = diag
                    break
            target = target or ordered[0]
        else:
            for diag in reversed(ordered):
                start = (diag.start_line, diag.start_char)
                end = (diag.end_line, diag.end_char)
                if start <= pos < end:
                    for earlier in reversed(ordered):
                        if (earlier.start_line, earlier.start_char) < start:
                            target = earlier
                            break
                    target = target or ordered[-1]
                    break
                if start <= pos and start != self._last_diag_jump:
                    target = diag
                    break
            target = target or ordered[-1]
        block = self.document().findBlockByNumber(target.start_line)
        if not block.isValid():
            return None
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            n=min(target.start_char, len(block.text())),
        )
        self.setTextCursor(cursor)
        self.centerCursor()
        self._last_diag_jump = (target.start_line, target.start_char)
        return target

    def event(self, event) -> bool:  # noqa: N802 (Qt API)
        if event.type() == QEvent.Type.ToolTip:
            help_event = event
            cursor = self.cursorForPosition(help_event.pos())
            diag = self.diagnostic_at(
                cursor.blockNumber(), cursor.positionInBlock()
            )
            if diag is not None:
                source = f"[{diag.source}] " if diag.source else ""
                QToolTip.showText(
                    help_event.globalPos(),
                    f"{diag.severity_label()}: {source}{diag.message}",
                    self,
                )
                return True
            QToolTip.hideText()
        return super().event(event)

    # ---- 缩进 ------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # 补全弹窗可见时优先把导航/确认键交给它
        if (
            self.completion_controller is not None
            and self.completion_controller.handle_key_press(event)
        ):
            return
        key = event.key()
        if (
            key == Qt.Key.Key_Space
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.completion_controller is not None
        ):
            self.completion_controller.trigger(force=True)
            return
        if key == Qt.Key.Key_Tab and self._spaces_instead_of_tabs:
            self._insert_indentation()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._insert_newline_with_indent(event):
                return
        super().keyPressEvent(event)

    def _insert_indentation(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._indent_selection(+1)
            return
        # 对齐到下一个 tab stop
        column = cursor.positionInBlock()
        spaces = self._tab_width - (column % self._tab_width)
        cursor.insertText(" " * spaces)

    def _indent_selection(self, direction: int) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.beginEditBlock()
        block = self.document().findBlock(start)
        end_block = self.document().findBlock(end)
        while block.isValid():
            pos = block.position()
            c = QTextCursor(self.document())
            c.setPosition(pos)
            line_text = block.text()
            if direction > 0:
                c.insertText(" " * self._tab_width)
            else:
                stripped = line_text[: self._tab_width]
                remove = len(stripped) - len(stripped.lstrip(" "))
                if remove:
                    c.setPosition(pos + remove, QTextCursor.MoveMode.KeepAnchor)
                    c.removeSelectedText()
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def _insert_newline_with_indent(self, event) -> bool:
        """回车时保留当前行前导缩进，块起始符结尾时自动增加一级缩进。

        适配 Python（``:``）与 C/C++/Java（``{``）两种块风格。
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        line = cursor.block().text()[: cursor.positionInBlock()]
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        if stripped.rstrip().endswith(("{", ":")):
            indent += " " * self._tab_width
        super().keyPressEvent(event)
        if indent:
            self.textCursor().insertText(indent)
        return True

    def cursor_position(self) -> tuple[int, int]:
        """返回 ``(行, 列)``，从 1 开始。"""
        cursor = self.textCursor()
        return cursor.blockNumber() + 1, cursor.positionInBlock() + 1
