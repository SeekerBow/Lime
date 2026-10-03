# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""cph.store：CPH 兼容的 .prob 存储测试。"""

from __future__ import annotations

import hashlib
import json
import os

from lime.cph.store import (
    TestCase,
    cph_directory,
    find_problem_file,
    load_problem,
    new_problem,
    path_hash,
    preferred_problem_path,
    save_problem,
)


def test_path_hash_is_md5_of_native_absolute_path(tmp_path):
    src = str(tmp_path / "A.cpp")
    assert path_hash(src) == hashlib.md5(os.path.abspath(src).encode()).hexdigest()


def test_problem_filename_matches_cph_layout(tmp_path):
    src = tmp_path / "A.cpp"
    target = preferred_problem_path(str(src))
    expected_name = f".A.cpp_{path_hash(str(src))}.prob"
    assert os.path.dirname(target) == cph_directory(str(src))
    assert os.path.basename(target) == expected_name
    assert os.path.basename(os.path.dirname(target)) == ".cph"


def test_save_and_load_roundtrip(tmp_path):
    src = tmp_path / "sum.py"
    problem = new_problem(str(src))
    problem.tests = [
        TestCase(id=123, input="1 2\n", output="3\n"),
        TestCase(id=456, input="10 20", output="30"),
    ]
    path = save_problem(problem)
    assert os.path.exists(path)

    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    # CPH 字段完整
    assert set(raw) == {
        "name", "url", "tests", "interactive", "memoryLimit",
        "timeLimit", "srcPath", "group", "local",
    }
    assert raw["local"] is True and raw["group"] == "local"
    assert raw["tests"][0] == {"id": 123, "input": "1 2\n", "output": "3\n"}

    loaded = load_problem(str(src))
    assert loaded is not None
    assert loaded.srcPath == os.path.abspath(str(src))
    assert [(c.id, c.input, c.output) for c in loaded.tests] == [
        (123, "1 2\n", "3\n"),
        (456, "10 20", "30"),
    ]


def test_load_real_cph_shaped_file(tmp_path):
    # 与真实 CPH 生成内容同构（含毫秒 id、url=源文件绝对路径）
    src = tmp_path / "A.cpp"
    cph_dir = tmp_path / ".cph"
    cph_dir.mkdir()
    payload = {
        "name": "Local: A",
        "url": str(src.resolve()),
        "tests": [{"id": 1742222829751, "input": "8\n", "output": "7\n"}],
        "interactive": False,
        "memoryLimit": 1024,
        "timeLimit": 3000,
        "srcPath": str(src.resolve()),
        "group": "local",
        "local": True,
    }
    prob_path = cph_dir / f".A.cpp_{path_hash(str(src))}.prob"
    prob_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_problem(str(src))
    assert loaded is not None
    assert loaded.timeLimit == 3000
    assert loaded.tests[0].id == 1742222829751
    assert loaded.tests[0].input == "8\n"


def test_find_problem_fallback_by_basename(tmp_path):
    # 从别的机器拷来的目录：hash 对不上，但同名 .prob 仍应被找到
    src = tmp_path / "B.cpp"
    cph_dir = tmp_path / ".cph"
    cph_dir.mkdir()
    foreign = cph_dir / ".B.cpp_0123456789abcdef0123456789abcdef.prob"
    foreign.write_text(
        json.dumps({
            "name": "Local: B",
            "url": "d:\\other\\B.cpp",
            "tests": [],
            "srcPath": "d:\\other\\B.cpp",
        }),
        encoding="utf-8",
    )
    assert find_problem_file(str(src)) == str(foreign)
    assert load_problem(str(src)).name == "Local: B"


def test_load_missing_returns_none(tmp_path):
    assert load_problem(str(tmp_path / "none.py")) is None
