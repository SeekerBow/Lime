# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""cph.checker：输出判定规则测试。"""

from __future__ import annotations

from lime.cph.checker import check_answer, normalize_output, whitespace_only_difference


def test_crlf_and_outer_trim_normalized():
    assert normalize_output("  3\r\n") == "3"


def test_accept_with_crlf_and_trailing_blank_lines():
    assert check_answer("3\n", "3\r\n\r\n") is True


def test_reject_wrong_value():
    assert check_answer("3\n", "4\n") is False


def test_whitespace_only_difference_detected():
    assert check_answer("1 2 3\n", "1  2  3\n") is False
    assert whitespace_only_difference("1 2 3\n", "1  2  3\n") is True
    assert whitespace_only_difference("1 2\n", "1 3\n") is False
