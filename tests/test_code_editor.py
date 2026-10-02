"""editor.code_editor 单元测试。"""

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor

from lime.editor.code_editor import CodeEditor


def _key(key, text=""):
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)


def test_basic_construction(qapp, settings):
    editor = CodeEditor()
    editor.apply_settings(settings)
    assert editor.font().family() == settings.font_family
    assert editor.cursor_position() == (1, 1)
    # 有行号栏且宽度为正
    assert editor.line_numbers_visible() is True
    assert editor.line_number_area_width() > 0


def test_line_number_width_grows(qapp):
    editor = CodeEditor()
    editor.setPlainText("\n".join(str(i) for i in range(100)))
    width_100 = editor.line_number_area_width()
    editor.setPlainText("1")
    width_1 = editor.line_number_area_width()
    assert width_100 > width_1


def test_toggle_line_numbers(qapp):
    editor = CodeEditor()
    assert editor.line_number_area_width() > 0
    editor.set_line_numbers_visible(False)
    assert editor.line_number_area_width() == 0
    assert editor.line_number_area.isVisible() is False


def test_tab_inserts_spaces(qapp, settings):
    settings.tab_width = 4
    settings.spaces_instead_of_tabs = True
    editor = CodeEditor()
    editor.apply_settings(settings)
    editor.keyPressEvent(_key(Qt.Key.Key_Tab))
    assert editor.toPlainText() == "    "


def test_tab_width_respected(qapp, settings):
    settings.tab_width = 2
    settings.spaces_instead_of_tabs = True
    editor = CodeEditor()
    editor.apply_settings(settings)
    editor.keyPressEvent(_key(Qt.Key.Key_Tab))
    assert editor.toPlainText() == "  "


def test_tab_stop_distance_follows_tab_width(qapp, settings):
    # 物理制表符的显示宽度必须同步（Qt 默认为约 8 字符，这对 C++ 过宽）
    settings.tab_width = 4
    editor = CodeEditor()
    editor.apply_settings(settings)
    expected = editor.fontMetrics().horizontalAdvance(" ") * 4
    assert editor.tabStopDistance() == pytest.approx(expected)

    editor.set_tab_width(2)
    expected_2 = editor.fontMetrics().horizontalAdvance(" ") * 2
    assert editor.tabStopDistance() == pytest.approx(expected_2)


def test_enter_indents_after_brace(qapp, settings):
    settings.tab_width = 4
    editor = CodeEditor()
    editor.apply_settings(settings)
    editor.setPlainText("int main() {")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    editor.keyPressEvent(_key(Qt.Key.Key_Return))
    assert editor.toPlainText() == "int main() {\n    "


def test_enter_keeps_indent_in_cpp_body(qapp, settings):
    settings.tab_width = 4
    editor = CodeEditor()
    editor.apply_settings(settings)
    editor.setPlainText("    return 0;")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    editor.keyPressEvent(_key(Qt.Key.Key_Return))
    assert editor.toPlainText().startswith("    return 0;\n    ")


def test_word_wrap_toggle(qapp):
    editor = CodeEditor()
    editor.set_word_wrap(True)
    assert editor.word_wrap() is True


def test_cursor_position_updates(qapp):
    editor = CodeEditor()
    editor.setPlainText("abc\ndef")
    cursor = editor.textCursor()
    cursor.setPosition(5)
    editor.setTextCursor(cursor)
    line, col = editor.cursor_position()
    assert (line, col) == (2, 2)
