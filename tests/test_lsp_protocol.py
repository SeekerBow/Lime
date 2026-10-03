# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""lime.lsp.protocol 纯逻辑单测：分帧、URI、数据结构、注册表、主题加载。"""

import os

import pytest

from lime.editor.highlighter import AVAILABLE_STYLES
from lime.editor.themes import get_style, is_dark, mix_color
from lime.lsp.protocol import (
    CompletionItem,
    Diagnostic,
    MessageFramer,
    TextEdit,
    encode_message,
    language_id_for_path,
    parse_completions,
    parse_diagnostics,
    path_to_uri,
    server_for_path,
    uri_to_path,
)


# ---- JSON-RPC 分帧 -------------------------------------------------------
def test_encode_message_has_content_length_header():
    raw = encode_message({"jsonrpc": "2.0", "method": "initialized"})
    assert raw.startswith(b"Content-Length: ")
    header, body = raw.split(b"\r\n\r\n", 1)
    assert int(header.split(b":", 1)[1].strip()) == len(body)
    assert b'"method":"initialized"' in body


def test_framer_handles_glued_and_split_packets():
    m1 = encode_message({"id": 1})
    m2 = encode_message({"id": 2})
    stream = m1 + m2

    framer = MessageFramer()
    # 逐字节喂入（极端半包）也必须正确切出两条
    messages = []
    for byte in stream:
        messages.extend(framer.feed(bytes([byte])))
    assert messages == [{"id": 1}, {"id": 2}]


def test_framer_waits_for_incomplete_body():
    raw = encode_message({"ok": True})
    framer = MessageFramer()
    assert framer.feed(raw[:10]) == []          # 头部都没到齐
    assert framer.feed(raw[10:30]) == []        # 仍不完整
    assert framer.feed(raw[30:]) == [{"ok": True}]


def test_framer_skips_garbage_headers():
    framer = MessageFramer()
    good = encode_message({"x": 1})
    out = framer.feed(b"Something-Else: 1\r\n\r\n" + good)
    assert out == [{"x": 1}]


# ---- URI -----------------------------------------------------------------
def test_uri_roundtrip_windows_drive():
    path = os.path.join("E:", os.sep, "Trae Projects", "main.cpp")
    uri = path_to_uri(path)
    assert uri.startswith("file:///E:")
    assert "%20" in uri
    assert os.path.normcase(uri_to_path(uri)) == os.path.normcase(path)


def test_uri_roundtrip_relative_becomes_absolute(tmp_path):
    path = str(tmp_path / "src" / "a.c")
    restored = uri_to_path(path_to_uri(path))
    assert os.path.normcase(restored) == os.path.normcase(path)


# ---- 诊断 / 补全解析 ------------------------------------------------------
def test_diagnostic_from_lsp_and_labels():
    diag = Diagnostic.from_lsp(
        {
            "range": {
                "start": {"line": 2, "character": 4},
                "end": {"line": 2, "character": 9},
            },
            "severity": 2,
            "message": "隐式声明",
            "source": "clang",
        }
    )
    assert (diag.start_line, diag.start_char, diag.end_line, diag.end_char) == (2, 4, 2, 9)
    assert diag.severity_label() == "警告"
    assert diag.message == "隐式声明"
    assert diag.source == "clang"
    assert Diagnostic.from_lsp({"range": {}}).severity_label() == "错误"


def test_parse_diagnostics_payload():
    diags = parse_diagnostics(
        {
            "uri": "file:///x",
            "diagnostics": [
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
                 "severity": 1, "message": "e1"},
                "garbage",
            ],
        }
    )
    assert len(diags) == 1
    assert diags[0].message == "e1"
    assert parse_diagnostics({}) == []


def test_completion_item_insert_fallback():
    item = CompletionItem.from_lsp({"label": "main"})
    assert item.insert_value == "main"
    detailed = CompletionItem.from_lsp(
        {"label": "printf", "insertText": "printf()", "detail": "-> int", "kind": 3}
    )
    assert detailed.insert_value == "printf()"
    assert detailed.kind == 3


def test_completion_text_edit_variants():
    plain_edit = CompletionItem.from_lsp(
        {
            "label": "printf",
            "textEdit": {
                "range": {
                    "start": {"line": 0, "character": 1},
                    "end": {"line": 0, "character": 4},
                },
                "newText": "printf",
            },
        }
    )
    assert isinstance(plain_edit.text_edit, TextEdit)
    assert plain_edit.insert_value == "printf"
    assert plain_edit.text_edit.start_char == 1

    insert_replace = CompletionItem.from_lsp(
        {
            "label": "printf",
            "textEdit": {
                "insert": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 2},
                },
                "replace": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 3},
                },
                "newText": "printf",
            },
        }
    )
    # InsertReplaceEdit 使用 insert 范围
    assert insert_replace.text_edit.end_char == 2


def test_parse_completions_shapes():
    assert parse_completions(None) == []
    items = parse_completions(
        [
            {"label": "a"},
            42,
        ]
    )
    assert [i.label for i in items] == ["a"]
    items = parse_completions({"items": [{"label": "b"}, {"label": "c"}]})
    assert [i.label for i in items] == ["b", "c"]


# ---- 服务器注册 -----------------------------------------------------------
@pytest.mark.parametrize(
    "filename,language",
    [
        ("a.c", "c"),
        ("a.h", "cpp"),
        ("a.cpp", "cpp"),
        ("a.cc", "cpp"),
        ("a.cxx", "cpp"),
        ("a.hpp", "cpp"),
        ("a.hxx", "cpp"),
        ("A.MM", "objective-cpp"),
    ],
)
def test_server_registry_maps_c_family(filename, language):
    spec = server_for_path(filename)
    assert spec is not None
    assert spec.key == "clangd"
    assert language_id_for_path(filename) == language


def test_server_registry_ignores_unsupported():
    assert server_for_path("script.py") is None
    assert language_id_for_path("notes.txt") is None
    assert "--background-index" in server_for_path("a.cpp").args


# ---- 自定义主题注册 -------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    ["one-dark-pro", "tokyo-night", "catppuccin-mocha", "github-dark-dimmed"],
)
def test_custom_themes_registered(name):
    assert name in AVAILABLE_STYLES
    style = get_style(name)
    # 背景色格式 #rrggbb
    assert style.background_color.startswith("#")
    assert is_dark(style.background_color)


def test_one_dark_pro_palette():
    style = get_style("one-dark-pro")
    assert style.background_color.lower() == "#282c34"


def test_get_style_falls_back_to_builtin():
    # 内置样式仍可取（例如 monokai）
    assert get_style("monokai") is not None


def test_mix_color_helper():
    assert mix_color("#000000", "#ffffff", 0.0).lower() == "#000000"
    assert mix_color("#000000", "#ffffff", 1.0).lower() == "#ffffff"
    middle = mix_color("#000000", "#ffffff", 0.5).lower()
    assert middle in ("#7f7f7f", "#808080")
