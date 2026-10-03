# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""search.find_replace 单元测试。"""

import re

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from lime.editor.code_editor import CodeEditor
from lime.search.find_replace import (
    FindReplaceBar,
    FindReplaceEngine,
    compile_pattern,
    find_all,
)


# ---- 纯逻辑 ----
def test_compile_case_insensitive_default():
    regex = compile_pattern("abc")
    assert regex.search("ABC")


def test_compile_case_sensitive():
    regex = compile_pattern("abc", case_sensitive=True)
    assert regex.search("abc")
    assert not regex.search("ABC")


def test_whole_word():
    matches = find_all("cat category cat", "cat", whole_word=True)
    assert matches == [(0, 3), (13, 16)]


def test_regex_mode():
    matches = find_all("a1 b2 c3", r"[a-z]\d", use_regex=True)
    assert len(matches) == 3


def test_plain_text_pattern_escaped():
    assert find_all("a.b", "a.b") == [(0, 3)]
    assert find_all("acb", "a.b") == []


def test_empty_pattern_no_matches():
    assert find_all("anything", "") == []


def test_invalid_regex_raises():
    with pytest.raises(re.error):
        compile_pattern("(unclosed", use_regex=True)


# ---- 引擎（基于真实编辑器）----
@pytest.fixture
def engine(qapp):
    editor = CodeEditor()
    editor.setPlainText("alpha beta alpha gamma")
    return FindReplaceEngine(editor)


def test_engine_count_and_find(engine):
    engine.set_pattern("alpha")
    assert engine.count() == 2
    assert engine.find() is True
    assert engine.editor.textCursor().selectedText() == "alpha"


def test_engine_find_backward_cycles(engine):
    engine.set_pattern("alpha")
    # 第一个匹配（0-5）
    assert engine.find() is True
    assert engine.editor.textCursor().selectionStart() == 0
    # 继续“上一个”：回绕到最后一个匹配（11-16）
    assert engine.find(backward=True) is True
    assert engine.editor.textCursor().selectionStart() == 11
    # 再“上一个”：回到第一个
    assert engine.find(backward=True) is True
    assert engine.editor.textCursor().selectionStart() == 0


def test_engine_no_match(engine):
    engine.set_pattern("zzz")
    assert engine.count() == 0
    assert engine.find() is False


def test_replace_all(engine):
    engine.set_pattern("alpha")
    count = engine.replace_all("ALPHA")
    assert count == 2
    assert engine.editor.toPlainText() == "ALPHA beta ALPHA gamma"


def test_replace_one_moves_forward(engine):
    engine.set_pattern("alpha")
    engine.find()
    assert engine.replace_one("ALPHA") is True
    text = engine.editor.toPlainText()
    assert text.startswith("ALPHA beta alpha")


def test_engine_regex_replace(qapp):
    editor = CodeEditor()
    editor.setPlainText("x1 x2 x3")
    engine = FindReplaceEngine(editor)
    engine.set_pattern(r"x(\d)")
    engine.options.use_regex = True
    count = engine.replace_all(r"n\1")
    assert count == 3
    assert editor.toPlainText() == "n1 n2 n3"


# ---- UI 工具条 ----
def test_bar_attach_count(qapp):
    editor = CodeEditor()
    editor.setPlainText("foo foo")
    bar = FindReplaceBar()
    bar.attach(editor)
    bar.find_input.setText("foo")
    assert "匹配 2 处" in bar.count_label.text()
    assert bar.find_next() is True


def test_bar_replace_all(qapp):
    editor = CodeEditor()
    editor.setPlainText("abc abc")
    bar = FindReplaceBar()
    bar.attach(editor)
    bar.find_input.setText("abc")
    bar.replace_input.setText("xyz")
    count = bar.replace_all()
    assert count == 2
    assert editor.toPlainText() == "xyz xyz"


def test_bar_hidden_by_default_and_close(qapp):
    bar = FindReplaceBar()
    assert bar.isVisible() is False
    bar.show_find()
    assert bar.isVisible() is True
    bar.hide_bar()
    assert bar.isVisible() is False


def test_bar_invalid_regex_message(qapp):
    editor = CodeEditor()
    editor.setPlainText("abc")
    bar = FindReplaceBar()
    bar.attach(editor)
    bar.regex_box.setChecked(True)
    bar.find_input.setText("(x")
    assert "正则无效" in bar.count_label.text()
