# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""样例数据存取，文件布局与 VSCode 插件 CPH 完全兼容。

存储布局（与 CPH 一致）::

    源文件目录/
        A.cpp
        .cph/
            .A.cpp_<md5(源文件绝对路径)>.prob

``.prob`` 为 JSON（CPH 本地题目格式）::

    {
      "name": "Local: A",
      "url": "<源文件绝对路径>",
      "tests": [{"id": 1742222829751, "input": "1 2\\n", "output": "3\\n"}],
      "interactive": false,
      "memoryLimit": 1024,
      "timeLimit": 3000,
      "srcPath": "<源文件绝对路径>",
      "group": "local",
      "local": true
    }
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import time
from dataclasses import dataclass, field

CPH_DIRNAME = ".cph"
DEFAULT_TIME_LIMIT_MS = 5000
DEFAULT_MEMORY_LIMIT_MB = 1024


@dataclass
class TestCase:
    """单条样例：输入与期望输出。"""

    id: int
    input: str = ""
    output: str = ""


@dataclass
class Problem:
    """一道题目的完整样例数据（对应一个 .prob 文件）。"""

    name: str
    url: str
    srcPath: str
    tests: list[TestCase] = field(default_factory=list)
    interactive: bool = False
    memoryLimit: int = DEFAULT_MEMORY_LIMIT_MB
    timeLimit: int = DEFAULT_TIME_LIMIT_MS
    group: str = "local"
    local: bool = True

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "tests": [
                {"id": case.id, "input": case.input, "output": case.output}
                for case in self.tests
            ],
            "interactive": self.interactive,
            "memoryLimit": self.memoryLimit,
            "timeLimit": self.timeLimit,
            "srcPath": self.srcPath,
            "group": self.group,
            "local": self.local,
        }

    @classmethod
    def from_json(cls, data: dict, src_path: str) -> "Problem":
        tests = []
        for index, raw in enumerate(data.get("tests", [])):
            tests.append(
                TestCase(
                    id=int(raw.get("id") or new_case_id() + index),
                    input=str(raw.get("input", "")),
                    output=str(raw.get("output", "")),
                )
            )
        return cls(
            name=str(data.get("name") or default_problem_name(src_path)),
            url=str(data.get("url") or src_path),
            srcPath=src_path,
            tests=tests,
            interactive=bool(data.get("interactive", False)),
            memoryLimit=int(data.get("memoryLimit", DEFAULT_MEMORY_LIMIT_MB)),
            timeLimit=int(data.get("timeLimit", DEFAULT_TIME_LIMIT_MS)),
            group=str(data.get("group", "local")),
            local=bool(data.get("local", True)),
        )


def new_case_id() -> int:
    """CPH 使用毫秒时间戳作为样例 id。"""
    return int(time.time() * 1000)


def default_problem_name(src_path: str) -> str:
    return f"Local: {os.path.splitext(os.path.basename(src_path))[0]}"


def cph_directory(src_path: str) -> str:
    """源文件旁的 .cph 目录路径。"""
    return os.path.join(os.path.dirname(os.path.abspath(src_path)), CPH_DIRNAME)


def path_hash(src_path: str) -> str:
    """CPH 命名规则：md5(操作系统原生绝对路径字符串)。"""
    return hashlib.md5(os.path.abspath(src_path).encode("utf-8")).hexdigest()


def preferred_problem_path(src_path: str) -> str:
    """CPH 标准文件名：``.cph/.<basename>_<md5>.prob``。"""
    src_path = os.path.abspath(src_path)
    return os.path.join(
        cph_directory(src_path),
        f".{os.path.basename(src_path)}_{path_hash(src_path)}.prob",
    )


def find_problem_file(src_path: str) -> str | None:
    """查找已有 .prob 文件。

    优先 CPH 标准命名（md5 与当前绝对路径一致）；否则回退匹配
    ``.<basename>_*.prob``（兼容从别处拷贝来的题目目录）。
    """
    src_path = os.path.abspath(src_path)
    standard = preferred_problem_path(src_path)
    if os.path.exists(standard):
        return standard

    pattern = os.path.join(
        cph_directory(src_path), f".{os.path.basename(src_path)}_*.prob"
    )
    candidates = sorted(glob.glob(pattern))
    # 内容里 srcPath 与当前路径一致的优先
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8") as fh:
                data = json.load(fh)
            if os.path.abspath(str(data.get("srcPath", ""))) == src_path:
                return candidate
        except (OSError, ValueError):
            continue
    return candidates[0] if candidates else None


def load_problem(src_path: str) -> Problem | None:
    """读取题目的样例数据；没有 .prob 文件时返回 None。"""
    path = find_problem_file(src_path)
    if path is None:
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return Problem.from_json(data, os.path.abspath(src_path))


def new_problem(src_path: str) -> Problem:
    """为本地源文件创建一个空题目（尚未落盘）。"""
    src_path = os.path.abspath(src_path)
    return Problem(name=default_problem_name(src_path), url=src_path, srcPath=src_path)


def save_problem(problem: Problem) -> str:
    """保存为 CPH 兼容的 .prob 文件，返回文件路径。"""
    target = preferred_problem_path(problem.srcPath)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(problem.to_json(), fh, ensure_ascii=False, indent=2)
    return target
