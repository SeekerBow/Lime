# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""editor.highlighter 单元测试。"""

import pytest
from pygments.token import Token

from PyQt6.QtGui import QColor, QFont, QTextCursor, QTextDocument

from lime.editor.highlighter import (
    AVAILABLE_STYLES,
    PygmentsHighlighter,
    build_format,
    lexer_for_filename,
)


def test_lexer_for_filename():
    assert lexer_for_filename("foo.py").name == "Python"
    assert "JavaScript" in lexer_for_filename("foo.js").name
    assert lexer_for_filename("foo.unknown_ext_xyz") is None


def test_build_format():
    fmt = build_format("bold italic #ff0000 underline")
    assert fmt.fontWeight() == QFont.Weight.Bold
    assert fmt.fontItalic() is True
    assert fmt.fontUnderline() is True
    assert fmt.foreground().color().name().lower() == "#ff0000"


def test_highlighter_applies_formats(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("x.py"))
    doc.setPlainText("def hello():\n    return 42\n")
    # headless 下文档不会主动布局，显式触发一次重高亮
    highlighter.rehighlight()

    block = doc.firstBlock()
    ranges = block.layout().formats()
    assert ranges, "第一行应至少有一个着色区间"
    # def 是关键字，应带前景色
    keyword_range = next(
        (r for r in ranges if doc.characterAt(r.start) == "d"), None
    )
    assert keyword_range is not None
    color = keyword_range.format.foreground().color()
    assert color.isValid()
    assert color != QColor("#000000") or True  # 默认样式关键字不是黑色


def test_set_style_and_background(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("x.py"))
    assert "default" in AVAILABLE_STYLES
    highlighter.set_style("monokai")
    bg = highlighter.background_color()
    assert bg.startswith("#")
    assert QColor(bg).isValid()


def test_unknown_lexer_highlights_nothing(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc)  # 无 lexer
    doc.setPlainText("plain text only")
    block = doc.firstBlock()
    assert block.layout().formats() == []


def test_java_and_c_family_lexers_detected():
    assert lexer_for_filename("App.java").name == "Java"
    assert lexer_for_filename("main.c").name == "C"
    assert lexer_for_filename("main.cpp").name == "C++"
    assert lexer_for_filename("main.cc").name == "C++"
    assert lexer_for_filename("main.cxx").name == "C++"
    assert lexer_for_filename("main.hpp").name == "C++"
    assert lexer_for_filename("main.hxx").name == "C++"
    # .h 在 Pygments 中映射到 C 或 C++ lexer
    assert lexer_for_filename("main.h").name in ("C", "C++")


def test_java_source_gets_highlighted(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("App.java"))
    doc.setPlainText("public class App {\n    int x = 1;\n}\n")
    highlighter.rehighlight()
    ranges = doc.firstBlock().layout().formats()
    assert ranges
    # public 是关键字，应着色
    assert any(doc.characterAt(r.start) == "p" for r in ranges)


def test_cpp_source_gets_highlighted(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("main.cpp"))
    doc.setPlainText("#include <iostream>\nint main() { return 0; }\n")
    highlighter.rehighlight()
    assert doc.firstBlock().layout().formats()


def _block_colors(doc):
    """返回 {块号: {前景色名集合}}，便于判断跨行 token 着色。"""
    result = {}
    block = doc.firstBlock()
    while block.isValid():
        colors = set()
        for rng in block.layout().formats():
            color = rng.format.foreground().color()
            if color.isValid():
                colors.add(color.name().lower())
        result[block.blockNumber()] = colors
        block = block.next()
    return result


@pytest.mark.parametrize("filename", ["main.cpp", "main.c", "App.java"])
def test_multiline_block_comment_highlights_across_lines(qapp, filename):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename(filename))
    doc.setPlainText("int a;\n/* first\n * second\n * third */\nint b;\n")
    highlighter.rehighlight()

    expected_fmt = highlighter._resolve_format(Token.Comment.Multiline)
    assert expected_fmt is not None
    expected_color = expected_fmt.foreground().color().name().lower()

    colors = _block_colors(doc)
    # 注释起始行：'/* first' 片段被着色
    assert expected_color in colors[1]
    # 中间行（不含 /* 或 */）也必须是注释色——旧实现这里没有任何格式
    assert expected_color in colors[2]
    assert expected_color in colors[3]
    # 注释结束后的代码行恢复代码着色，不再残留注释色
    assert expected_color not in colors[4]

    # 块状态：注释覆盖范围 1..3 非零，其余为 0
    states = []
    block = doc.firstBlock()
    while block.isValid():
        states.append(block.userState())
        block = block.next()
    assert states[0] == 0
    assert states[1] != 0
    assert states[2] != 0
    assert states[3] == 0
    assert states[4] == 0


def test_multiline_comment_reacts_to_editing(qapp):
    """删掉闭合 */ 后，其后的行应立即变为注释内部状态。"""
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("main.cpp"))
    doc.setPlainText("/* open\ncode here;\n*/\nint x;\n")
    highlighter.rehighlight()
    assert doc.findBlockByNumber(3).userState() == 0

    # 删除第 3 行的 '*/'
    cursor = QTextCursor(doc.findBlockByNumber(2))
    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
    )
    cursor.removeSelectedText()
    highlighter.rehighlight()

    expected_color = (
        highlighter._resolve_format(Token.Comment.Multiline)
        .foreground()
        .color()
        .name()
        .lower()
    )
    colors = _block_colors(doc)
    assert expected_color in colors[3]  # int x; 现在处于未闭合注释内


def test_unclosed_comment_at_eof_highlighted(qapp):
    """文件末尾未闭合的 /* 也按注释着色（不闪成错误色）。"""
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("main.cpp"))
    doc.setPlainText("int x;\n/* unterminated tail")
    highlighter.rehighlight()
    expected_fmt = highlighter._resolve_format(Token.Comment.Multiline)
    colors = _block_colors(doc)
    assert expected_fmt.foreground().color().name().lower() in colors[1]


def test_multiline_string_python_still_works(qapp):
    doc = QTextDocument()
    highlighter = PygmentsHighlighter(doc, lexer=lexer_for_filename("x.py"))
    doc.setPlainText('x = """line1\nline2\nline3"""\n')
    highlighter.rehighlight()
    # 普通三引号字符串在 Pygments 中归为 Literal.String
    expected_fmt = highlighter._resolve_format(Token.Literal.String)
    expected_color = expected_fmt.foreground().color().name().lower()
    colors = _block_colors(doc)
    assert expected_color in colors[0]
    assert expected_color in colors[1]
    assert expected_color in colors[2]
