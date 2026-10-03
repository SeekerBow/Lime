# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""输出比对：判定规则与 CPH 一致。"""

from __future__ import annotations


def normalize_output(text: str) -> str:
    r"""CPH 规则：``\\r\\n`` 归一为 ``\\n``，去掉首尾空白。"""
    return text.replace("\r\n", "\n").strip()


def check_answer(expected: str, actual: str) -> bool:
    """与 CPH 相同的严格判定：仅做换行归一与首尾 trim 后整体比较。"""
    return normalize_output(actual) == normalize_output(expected)


def whitespace_only_difference(expected: str, actual: str) -> bool:
    """严格比较失败时，进一步判断是否只是空白差异（提示用）。"""
    return normalize_output(expected).split() == normalize_output(actual).split()
