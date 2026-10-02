"""terminal 模块单元测试：ANSI 清理纯函数 + 真实 Shell 集成。"""

import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from lime.terminal.terminal import (
    TerminalWidget,
    decode_process_bytes,
    default_shell,
    encode_process_input,
    strip_ansi,
)
from tests.conftest import wait_for


def test_decode_utf8_output():
    assert decode_process_bytes("print('你好')\n".encode("utf-8")) == "print('你好')\n"


def test_decode_falls_back_to_gbk():
    # 中文 Windows 编译器诊断常见的 GBK 输出
    data = "错误: 需要';'".encode("gbk")
    text = decode_process_bytes(data)
    assert "错误" in text


def test_decode_ascii_unchanged():
    assert decode_process_bytes(b"hello\r\n") == "hello\r\n"


def test_strip_csi_colors():
    assert strip_ansi("\x1b[31mred\x1b[0m text") == "red text"


def test_strip_cursor_movement():
    assert strip_ansi("abc\x1b[2Kdef") == "abcdef"


def test_strip_osc_title():
    assert strip_ansi("\x1b]0;window title\x07prompt>") == "prompt>"


def test_strip_bell_and_crlf():
    assert strip_ansi("a\x07b\r\nc") == "ab\nc"


def test_strip_backspace_emulation():
    # "ab" + BS 实际删除 b
    assert strip_ansi("ab\x08c") == "ac"


def test_default_shell():
    program, args = default_shell()
    if sys.platform.startswith("win"):
        assert program.lower().endswith("cmd.exe")
        assert args == []
    else:
        assert "bash" in program or program.endswith("sh")


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_cmd_echo_roundtrip(qapp, settings):
    terminal = TerminalWidget(settings)
    try:
        assert terminal.start_shell() is True
        assert terminal.is_running() is True
        terminal.send_command("echo lime_terminal_token_777")
        ok = wait_for(
            lambda: "lime_terminal_token_777" in terminal.toPlainText(),
            timeout_ms=20000,
        )
        assert ok, terminal.toPlainText()
    finally:
        terminal.stop_shell()
    assert terminal.is_running() is False


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_keyboard_typing_in_input_box_reaches_cmd(qapp, settings):
    # 在底部命令输入框打字并按回车，命令必须到达 cmd
    terminal = TerminalWidget(settings)
    try:
        terminal.show()
        assert terminal.start_shell() is True
        QTest.qWait(800)
        assert terminal.input_edit.isEnabled() is True
        QTest.keyClicks(terminal.input_edit, "echo keytoken_55")
        QTest.keyClick(
            terminal.input_edit,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        ok = wait_for(
            lambda: "keytoken_55" in terminal.toPlainText(),
            timeout_ms=20000,
        )
        assert ok, terminal.toPlainText()
        # 发送后输入框清空
        assert terminal.input_edit.toPlainText() == ""
    finally:
        terminal.stop_shell()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_shift_enter_keeps_lines_then_enter_sends_all(qapp, settings):
    # Shift+Enter 在输入框内换行且不发送；普通 Enter 把多行一起发给 cmd
    terminal = TerminalWidget(settings)
    try:
        terminal.show()
        assert terminal.start_shell() is True
        QTest.qWait(800)
        box = terminal.input_edit
        QTest.keyClicks(box, "echo ml_line1")
        QTest.keyClick(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(box, "echo ml_line2")
        # 尚未按回车：两行都保留在输入框里，且没有任何命令被执行
        assert box.toPlainText() == "echo ml_line1\necho ml_line2"
        QTest.qWait(400)
        assert "ml_line1" not in terminal.toPlainText()

        QTest.keyClick(box, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        assert wait_for(
            lambda: "ml_line1" in terminal.toPlainText()
            and "ml_line2" in terminal.toPlainText(),
            timeout_ms=20000,
        ), terminal.toPlainText()
        assert box.toPlainText() == ""
    finally:
        terminal.stop_shell()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_input_box_disabled_when_shell_not_running(qapp, settings):
    terminal = TerminalWidget(settings)
    assert terminal.input_edit.isEnabled() is False
    try:
        terminal.start_shell()
        assert terminal.input_edit.isEnabled() is True
        terminal.stop_shell()
        QTest.qWait(300)
        assert terminal.input_edit.isEnabled() is False
    finally:
        terminal.stop_shell()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows 编码")
def test_encode_input_windows_prefers_mbcs():
    # 中文按系统 ANSI 代码页（GBK）编码，匹配 cin/input 的解析预期
    assert encode_process_input("你好") == "你好".encode("gbk")
    assert encode_process_input("abc") == b"abc"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_ime_commit_text_reaches_cmd(qapp, settings):
    # 回归：中文输入法向可编辑输入框提交文字，回车后到达 cmd
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QInputMethodEvent

    terminal = TerminalWidget(settings)
    try:
        terminal.show()
        assert terminal.start_shell() is True
        QTest.qWait(800)
        terminal.input_edit.setFocus()
        event = QInputMethodEvent()
        event.setCommitString("echo ime_token_55")
        QCoreApplication.sendEvent(terminal.input_edit, event)
        assert terminal.input_edit.toPlainText() == "echo ime_token_55"
        QTest.keyClick(
            terminal.input_edit,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        ok = wait_for(
            lambda: "ime_token_55" in terminal.toPlainText(),
            timeout_ms=20000,
        )
        assert ok, terminal.toPlainText()
    finally:
        terminal.stop_shell()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows cmd 集成测试")
def test_terminal_restart(qapp, settings):
    terminal = TerminalWidget(settings)
    try:
        terminal.start_shell()
        terminal.send_command("echo before_token")
        assert wait_for(lambda: "before_token" in terminal.toPlainText())
        terminal.restart_shell()
        assert terminal.is_running() is True
        terminal.send_command("echo after_token")
        assert wait_for(lambda: "after_token" in terminal.toPlainText())
    finally:
        terminal.stop_shell()
