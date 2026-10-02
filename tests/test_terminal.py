"""terminal 模块单元测试：ANSI 清理纯函数 + 真实 Shell 集成。"""

import sys

import pytest

from lime.terminal.terminal import (
    TerminalWidget,
    decode_process_bytes,
    default_shell,
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
