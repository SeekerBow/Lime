# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""cph.judge：真实子进程评测集成测试。"""

from __future__ import annotations

import shutil
import sys

import pytest

from lime.cph.judge import (
    VERDICT_ACCEPTED,
    VERDICT_RUNTIME,
    VERDICT_TIMEOUT,
    VERDICT_WRONG,
    JudgeController,
)
from lime.cph.store import TestCase
from tests.conftest import wait_for

IS_WINDOWS = sys.platform.startswith("win")
HAS_GPP = shutil.which("g++") is not None


def _run(qapp, path, cases, timeout_ms=10000):
    controller = JudgeController()
    finished: list[list] = []
    failed: list[str] = []
    compile_log: list[tuple] = []
    controller.all_finished.connect(lambda results: finished.append(results))
    controller.judge_failed.connect(lambda msg: failed.append(msg))
    controller.compile_finished.connect(lambda ok, out: compile_log.append((ok, out)))
    assert controller.run_cases(str(path), cases, timeout_ms=timeout_ms) is True
    assert wait_for(lambda: bool(finished), timeout_ms=60000)
    return finished[0], failed, compile_log


def test_python_two_cases_pass_and_wrong(qapp, tmp_path):
    script = tmp_path / "ab.py"
    script.write_text(
        "a, b = map(int, input().split())\nprint(a + b)\n",
        encoding="utf-8",
    )
    cases = [
        TestCase(id=1, input="20 22\n", output="42\n"),
        TestCase(id=2, input="1 1\n", output="3\n"),
    ]
    results, failed, _ = _run(qapp, script, cases)
    assert failed == []
    assert [r.case_id for r in results] == [1, 2]
    assert results[0].verdict == VERDICT_ACCEPTED
    assert results[1].verdict == VERDICT_WRONG
    assert "3" not in results[1].actual or results[1].actual.strip() != "3"
    assert results[0].elapsed_ms >= 0


def test_python_timeout(qapp, tmp_path):
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    results, _, _ = _run(qapp, script, [TestCase(id=9, input="", output="")], 500)
    assert results[0].verdict == VERDICT_TIMEOUT


def test_runtime_error_reported(qapp, tmp_path):
    script = tmp_path / "boom.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    results, _, _ = _run(qapp, script, [TestCase(id=7, input="", output="")])
    assert results[0].verdict == VERDICT_RUNTIME


def test_unsupported_extension_emits_failure(qapp, tmp_path):
    binary = tmp_path / "note.txt"
    binary.write_text("hello", encoding="utf-8")
    controller = JudgeController()
    failed: list[str] = []
    controller.judge_failed.connect(lambda msg: failed.append(msg))
    assert controller.run_cases(str(binary), [TestCase(id=1)]) is False
    assert failed and "不支持" in failed[0]


def test_stdin_eof_allows_read_all(qapp, tmp_path):
    # 程序读到 EOF 为止：closeWriteChannel 必须生效
    script = tmp_path / "sumall.py"
    script.write_text(
        "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
        encoding="utf-8",
    )
    results, _, _ = _run(
        qapp, script, [TestCase(id=3, input="1\n2\n3\n4\n", output="10\n")]
    )
    assert results[0].verdict == VERDICT_ACCEPTED


@pytest.mark.skipif(not IS_WINDOWS or not HAS_GPP, reason="Windows + g++")
def test_compiled_cpp_judged_once_per_case(qapp, tmp_path):
    source = tmp_path / "ask.cpp"
    source.write_text(
        "#include <iostream>\n"
        "int main(){ int a,b; std::cin>>a>>b; std::cout<<a*b<<std::endl; }\n",
        encoding="utf-8",
    )
    results, failed, compile_log = _run(
        qapp,
        source,
        [
            TestCase(id=11, input="6 7\n", output="42\n"),
            TestCase(id=12, input="0 5\n", output="1\n"),
        ],
    )
    assert failed == []
    assert compile_log and compile_log[0][0] is True
    assert results[0].verdict == VERDICT_ACCEPTED
    assert results[1].verdict == VERDICT_WRONG


@pytest.mark.skipif(not IS_WINDOWS or not HAS_GPP, reason="Windows + g++")
def test_compile_failure_reported(qapp, tmp_path):
    source = tmp_path / "bad.cpp"
    source.write_text("int main( {{{\n", encoding="utf-8")
    results, _failed, compile_log = _run(qapp, source, [TestCase(id=1)])
    assert results == []
    assert compile_log and compile_log[0][0] is False
    assert compile_log[0][1].strip() != ""
