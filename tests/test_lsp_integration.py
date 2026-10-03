# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""LSP 端到端测试：假服务器、（可选）真实 clangd、补全/诊断 UI。"""

from __future__ import annotations

import os
import shutil
import sys

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from lime.editor.code_editor import CodeEditor
from lime.lsp.client import READY, LspClient
from lime.lsp.completion import (
    CompletionController,
    apply_completion,
    filter_items,
    strip_snippets,
)
from lime.lsp.problems_panel import ProblemsPanel
from lime.lsp.protocol import (
    CLANGD,
    CompletionItem,
    Diagnostic,
    TextEdit,
    path_to_uri,
)
from lime.lsp.service import LspService
from tests.conftest import wait_for

# --------------------------------------------------------------------------
# 假 LSP 服务器（stdio JSON-RPC）
# --------------------------------------------------------------------------
FAKE_SERVER = r'''
import json
import sys


def read_message(buf):
    # Windows 管道上 read(n) 会阻塞到读满 n 字节，必须用 read1 做半包缓冲
    while b"\r\n\r\n" not in buf:
        chunk = sys.stdin.buffer.read1(4096)
        if not chunk:
            return None, buf
        buf += chunk
    header, rest = buf.split(b"\r\n\r\n", 1)
    length = 0
    for line in header.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    while len(rest) < length:
        chunk = sys.stdin.buffer.read1(length - len(rest))
        if not chunk:
            break
        rest += chunk
    return json.loads(rest[:length].decode("utf-8")), rest[length:]


def send(msg):
    body = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()


buf = b""
while True:
    msg, buf = read_message(buf)
    if msg is None:
        break
    method = msg.get("method")
    if method == "initialize":
        send({
            "jsonrpc": "2.0", "id": msg["id"],
            "result": {"capabilities": {
                "completionProvider": {"triggerCharacters": [".", ">", ":"]}}},
        })
    elif method == "textDocument/didOpen":
        uri = msg["params"]["textDocument"]["uri"]
        send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
              "params": {"uri": uri, "diagnostics": [{
                  "range": {"start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 3}},
                  "severity": 1, "message": "fake error", "source": "fake"}]}})
    elif method == "textDocument/completion":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"items": [
            {"label": "printf", "insertText": "printf", "detail": "-> int", "kind": 3},
            {"label": "fprintf", "insertText": "fprintf", "kind": 3},
        ]}})
'''


@pytest.fixture
def fake_server(tmp_path):
    script = tmp_path / "fake_lsp_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    return script


# --------------------------------------------------------------------------
# LspClient × 假服务器
# --------------------------------------------------------------------------
def test_client_initialize_diagnostics_completion(qapp, fake_server):
    client = LspClient("fake", sys.executable, [str(fake_server)], str(fake_server.parent))
    failures = []
    client.failed.connect(lambda msg: failures.append(msg))
    client.start()
    try:
        assert wait_for(lambda: client.state == READY, 15000), "假服务器 initialize 超时"
        assert failures == []
        assert "." in client.completion_triggers

        uri = path_to_uri(str(fake_server.parent / "main.cpp"))
        received_diags = []
        client.diagnosticsReceived.connect(lambda _u, items: received_diags.append(items))
        client.did_open(uri, "cpp", "int main(){}\n")
        assert wait_for(lambda: bool(received_diags), 10000)
        diags = received_diags[0]
        assert diags and diags[0].message == "fake error"

        received_items = []
        client.completionReceived.connect(lambda _rid, items: received_items.append(items))
        req_id = client.request_completion(uri, 0, 5)
        assert req_id > 0
        assert wait_for(lambda: bool(received_items), 10000)
        labels = [item.label for item in received_items[0]]
        assert "printf" in labels
    finally:
        client.stop()


def test_client_reports_failed_to_start(qapp):
    client = LspClient(
        "nope", "definitely-not-a-real-lsp-server-xyz-123", [], os.getcwd()
    )
    failures = []
    client.failed.connect(lambda msg: failures.append(msg))
    client.start()
    try:
        assert wait_for(lambda: bool(failures), 5000)
        assert "无法启动" in failures[0]
    finally:
        client.stop()


# --------------------------------------------------------------------------
# LspService × 假服务器
# --------------------------------------------------------------------------
def test_service_doc_lifecycle_and_diagnostics(
    qapp, settings, fake_server
):
    source = fake_server.parent / "main.cpp"
    source.write_text("int main(){}\n", encoding="utf-8")

    service = LspService(settings)
    diagnostics = {}
    service.diagnosticsReceived.connect(
        lambda path, items: diagnostics.__setitem__(path, items)
    )

    # 把 service 内部的服务器创建替换为假服务器（无额外参数）
    def ensure_with_fake(spec, root_dir):
        existing = service._clients.get(spec.key)
        if existing is not None:
            return existing
        client = LspClient(spec.key, sys.executable, [str(fake_server)], root_dir, service)
        client.initialized.connect(lambda k=spec.key: service._on_initialized(k))
        client.failed.connect(
            lambda msg, k=spec.key: service.serverStatus.emit(k, msg)
        )
        client.diagnosticsReceived.connect(service._on_diagnostics)
        client.completionReceived.connect(service.completionReceived.emit)
        service._clients[spec.key] = client
        client.start()
        return client

    service._ensure_client = ensure_with_fake
    try:
        service.on_opened(str(source), "int main(){}\n")
        assert wait_for(
            lambda: service.is_server_ready("clangd"), 15000
        ), "假服务器未就绪"
        assert wait_for(lambda: bool(diagnostics), 10000)
        assert any(os.path.normcase(str(source)) == p for p in diagnostics)

        # 修改（防抖 300ms）与保存/关闭不应报错
        service.on_changed(str(source), "int main(){ int x=1; }\n")
        assert wait_for(lambda: True, 400)
        service.on_saved(str(source), "int main(){ int x=1; }\n")
        service.on_closed(str(source))
    finally:
        service.shutdown()


def test_service_disabled_does_nothing(qapp, settings):
    settings.lsp_enabled = False
    service = LspService(settings)
    service.on_opened("whatever.cpp", "int x;")
    assert service.request_completion("whatever.cpp", 0, 1) == -1


# --------------------------------------------------------------------------
# 真实 clangd（安装时才跑）
# --------------------------------------------------------------------------
HAS_CLANGD = shutil.which("clangd") is not None


@pytest.mark.skipif(not HAS_CLANGD, reason="环境中未安装 clangd")
def test_real_clangd_diagnostics_and_completion(qapp, tmp_path):
    source = tmp_path / "main.cpp"
    source.write_text(
        "#include <cstdio>\n"
        "int main() {\n"
        "    undefined_symbol_xyz();\n"
        "    pri\n"
        "}\n",
        encoding="utf-8",
    )
    client = LspClient(
        "clangd", shutil.which("clangd"), list(CLANGD.args), str(tmp_path)
    )
    failures = []
    client.failed.connect(lambda msg: failures.append(msg))
    client.start()
    try:
        assert wait_for(lambda: client.state == READY, 30000), failures
        uri = path_to_uri(str(source))

        received = []
        client.diagnosticsReceived.connect(lambda _u, items: received.append(items))
        client.did_open(uri, "cpp", source.read_text(encoding="utf-8"))

        def has_error():
            return any(
                any(d.severity == 1 for d in items) for items in received
            )

        assert wait_for(has_error, 30000), "clangd 未报告预期的未定义标识符错误"

        items_box = []
        client.completionReceived.connect(lambda _rid, items: items_box.append(items))
        req_id = client.request_completion(uri, 3, 7)
        assert req_id > 0
        assert wait_for(lambda: any(items_box), 30000)
        labels = [item.label.lower() for item in items_box[0]]
        assert any("pri" in label for label in labels), labels[:10]
    finally:
        client.stop()


# --------------------------------------------------------------------------
# 补全纯逻辑与 UI
# --------------------------------------------------------------------------
def test_strip_snippets():
    assert strip_snippets("printf(${1:...});$0") == "printf(...);"
    assert strip_snippets("plain") == "plain"


def test_filter_items_orders_by_prefix():
    items = [CompletionItem(label=x) for x in ("fprintf", "printf", "sprintf", "puts")]
    filtered = [i.label for i in filter_items(items, "pri")]
    assert filtered[0] == "printf"
    assert "sprintf" in filtered
    assert "puts" not in filtered
    assert filter_items(items, "")[:60]  # 空前缀不过滤


def test_apply_completion_replaces_prefix_and_textedit(qapp):
    editor = CodeEditor()
    editor.setPlainText("hello pri")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    apply_completion(editor, CompletionItem(label="printf", insert_text="printf"), "pri")
    assert editor.toPlainText() == "hello printf"

    # textEdit 优先于前缀
    item = CompletionItem(
        label="fprintf",
        insert_text="fprintf",
        text_edit=TextEdit(0, 6, 0, 13, "fprintf"),
    )
    apply_completion(editor, item, "printf")
    assert editor.toPlainText() == "hello fprintf"


def test_completion_controller_popup_and_keyboard(qapp):
    editor = CodeEditor()
    editor.setPlainText("x.pri")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    from lime.core.settings import Settings

    service = LspService(Settings())
    controller = CompletionController(editor, service, path_provider=lambda: None)

    items = [
        CompletionItem(label="printf", insert_text="printf", detail="-> int"),
        CompletionItem(label="print"),
    ]
    controller._prefix = "pri"
    controller._request_id = 1
    service.completionReceived.emit(1, items)
    assert controller.popup.isVisible()
    assert controller.popup.count() == 2
    assert controller.popup.current_item().label == "printf"

    # Esc 关闭并消费事件
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert controller.handle_key_press(esc) is True
    assert not controller.popup.isVisible()

    # 再次弹出，Tab 确认插入
    service.completionReceived.emit(1, items)
    assert controller.popup.isVisible()
    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert controller.handle_key_press(tab) is True
    assert editor.toPlainText() == "x.printf"


def test_completion_controller_hides_on_no_path(qapp):
    editor = CodeEditor()
    from lime.core.settings import Settings

    service = LspService(Settings())
    controller = CompletionController(editor, service, path_provider=lambda: None)
    # 无路径（未命名文档）触发不弹窗
    controller.trigger(force=True)
    assert not controller.popup.isVisible()


# --------------------------------------------------------------------------
# 问题面板 / 编辑器诊断
# --------------------------------------------------------------------------
def test_problems_panel_lists_and_jumps(qapp):
    panel = ProblemsPanel()
    diags = [
        Diagnostic(0, 0, 0, 3, severity=1, message="错误一", source="clang"),
        Diagnostic(2, 1, 2, 4, severity=2, message="警告一"),
    ]
    total = panel.update_file(os.path.join("E:", "proj", "main.cpp"), diags)
    assert total == 2
    assert panel.list_widget.count() == 2
    assert "错误" in panel.summary.text()
    assert "警告" in panel.summary.text()

    jumped = []
    panel.open_requested.connect(lambda p, l, c: jumped.append((p, l, c)))
    panel.list_widget.setCurrentRow(0)
    panel.list_widget.itemActivated.emit(panel.list_widget.currentItem())
    assert jumped and jumped[0][1] == 0 and jumped[0][2] == 0

    # 清空该文件诊断
    assert panel.update_file(os.path.join("E:", "proj", "main.cpp"), []) == 0
    assert panel.list_widget.count() == 0


def test_editor_diagnostics_hover_and_goto(qapp):
    editor = CodeEditor()
    editor.setPlainText("abc\nxyz\n")
    diags = [
        Diagnostic(0, 0, 0, 3, severity=1, message="bad", source="clang"),
        Diagnostic(1, 0, 1, 3, severity=2, message="warn"),
    ]
    editor.set_diagnostics(diags)
    assert editor.diagnostics() == diags
    assert editor.diagnostic_at(0, 1).message == "bad"
    assert editor.diagnostic_at(5, 0) is None

    # 从文件起点 F8 -> 第一条；再下一条；循环回到第一条
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.Start)
    editor.setTextCursor(cursor)
    first = editor.goto_next_diagnostic(forward=True)
    assert first is diags[0]
    second = editor.goto_next_diagnostic(forward=True)
    assert second is diags[1]
    wrapped = editor.goto_next_diagnostic(forward=True)
    assert wrapped is diags[0]
