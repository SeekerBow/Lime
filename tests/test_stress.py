# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""cph.stress / cph.stress_panel：一键对拍的真实子进程集成测试。"""

from __future__ import annotations

import shutil
import sys

import pytest

from lime.cph.stress import StressController
from lime.cph.stress_panel import StressPanel
from tests.conftest import wait_for

IS_WINDOWS = sys.platform.startswith("win")
HAS_GPP = shutil.which("g++") is not None

GEN_PY = "import sys\nn = int(sys.argv[1])\nprint(n, n + 1)\n"
STD_PY = "a, b = map(int, input().split())\nprint(a + b)\n"
MY_GOOD_PY = STD_PY
MY_BAD_PY = "a, b = map(int, input().split())\nprint(0 if a == 5 else a + b)\n"
MY_FLOAT_PY = "a, b = map(int, input().split())\nprint(float(a + b))\n"
CHECKER_PY = (
    "import sys\n"
    "with open(sys.argv[2]) as f:\n"
    "    out = f.read().split()\n"
    "with open(sys.argv[3]) as f:\n"
    "    ans = f.read().split()\n"
    "ok = len(out) == len(ans) and all(\n"
    "    abs(float(x) - float(y)) < 1e-6 for x, y in zip(out, ans)\n"
    ")\n"
    "sys.exit(0 if ok else 1)\n"
)


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _programs(tmp_path, my_source=MY_GOOD_PY):
    gen = _write(tmp_path, "gen.py", GEN_PY)
    std = _write(tmp_path, "std.py", STD_PY)
    my = _write(tmp_path, "my.py", my_source)
    return gen, my, std


class _Harness:
    """收集控制器信号，等待运行结束。"""

    def __init__(self):
        self.controller = StressController()
        self.failures = []
        self.fatal = []
        self.finished = []
        self.controller.test_failed.connect(self.failures.append)
        self.controller.stress_failed.connect(self.fatal.append)
        self.controller.all_finished.connect(lambda p, t: self.finished.append((p, t)))

    def run(self, gen, my, std, checker="", rounds=5, timeout_ms=10000):
        ok = self.controller.start(
            gen, my, std, checker, rounds=rounds, timeout_ms=timeout_ms
        )
        if ok:
            assert wait_for(lambda: bool(self.finished), timeout_ms=60000)
        return ok


def test_all_pass(qapp, tmp_path):
    gen, my, std = _programs(tmp_path)
    h = _Harness()
    assert h.run(gen, my, std, rounds=5)
    assert h.fatal == []
    assert h.failures == []
    assert h.finished == [(5, 5)]


def test_failure_shows_round_detail(qapp, tmp_path):
    gen, my, std = _programs(tmp_path, MY_BAD_PY)
    h = _Harness()
    assert h.run(gen, my, std, rounds=10)
    assert h.fatal == []
    assert len(h.failures) == 1
    failure = h.failures[0]
    assert failure.index == 5
    assert failure.input.split() == ["5", "6"]
    assert failure.my_output.strip() == "0"
    assert failure.std_output.strip() == "11"
    # 出错即停：只完成了前 4 轮
    assert h.finished == [(4, 10)]


def test_spj_accepts_float_format(qapp, tmp_path):
    gen, my, std = _programs(tmp_path, MY_FLOAT_PY)
    checker = _write(tmp_path, "checker.py", CHECKER_PY)
    h = _Harness()
    assert h.run(gen, my, std, checker, rounds=3)
    assert h.fatal == []
    assert h.failures == []
    assert h.finished == [(3, 3)]


def test_without_spj_float_format_fails(qapp, tmp_path):
    gen, my, std = _programs(tmp_path, MY_FLOAT_PY)
    h = _Harness()
    assert h.run(gen, my, std, rounds=3)
    assert len(h.failures) == 1
    assert h.failures[0].my_output.strip() == "3.0"
    assert h.failures[0].std_output.strip() == "3"


def test_my_timeout_reported_as_failure(qapp, tmp_path):
    gen, my, std = _programs(tmp_path, "import time\ntime.sleep(5)\n")
    h = _Harness()
    assert h.run(gen, my, std, rounds=1, timeout_ms=500)
    assert len(h.failures) == 1
    assert "待测程序" in h.failures[0].message
    assert "被终止" in h.failures[0].message


def test_broken_generator_is_fatal(qapp, tmp_path):
    gen, my, std = _programs(tmp_path)
    bad_gen = _write(tmp_path, "gen_bad.py", "import sys\nsys.exit(2)\n")
    h = _Harness()
    assert h.run(bad_gen, my, std, rounds=3)
    assert h.failures == []
    assert h.fatal and "数据生成器" in h.fatal[0]
    assert h.finished == [(0, 3)]


def test_invalid_path_rejected(qapp, tmp_path):
    gen, my, std = _programs(tmp_path)
    h = _Harness()
    assert h.run(str(tmp_path / "nope.py"), my, std) is False
    assert h.fatal and "路径无效" in h.fatal[0]


def test_unsupported_extension_rejected(qapp, tmp_path):
    gen, my, std = _programs(tmp_path)
    note = _write(tmp_path, "note.txt", "hello")
    h = _Harness()
    assert h.run(gen, my, note) is False
    assert h.fatal and "不支持" in h.fatal[0]


def test_stop_midway(qapp, tmp_path):
    gen, my, std = _programs(tmp_path)
    h = _Harness()
    h.controller.progress.connect(lambda *_: h.controller.stop())
    assert h.run(gen, my, std, rounds=100000)
    passed, total = h.finished[0]
    assert total == 100000
    assert passed < total


@pytest.mark.skipif(not IS_WINDOWS or not HAS_GPP, reason="Windows + g++")
def test_compiled_cpp_end_to_end(qapp, tmp_path):
    gen = _write(
        tmp_path,
        "gen.cpp",
        "#include <cstdlib>\n#include <iostream>\n"
        "int main(int argc, char** argv){ int n = std::atoi(argv[1]);"
        " std::cout << n << ' ' << n + 1 << std::endl; }\n",
    )
    std = _write(
        tmp_path,
        "std.cpp",
        "#include <iostream>\n"
        "int main(){ long long a,b; std::cin>>a>>b; std::cout<<a+b<<std::endl; }\n",
    )
    my_good = _write(
        tmp_path,
        "my.cpp",
        "#include <iostream>\n"
        "int main(){ long long a,b; std::cin>>a>>b; std::cout<<a+b<<std::endl; }\n",
    )
    h = _Harness()
    assert h.run(gen, my_good, std, rounds=5)
    assert h.fatal == []
    assert h.finished == [(5, 5)]

    my_bad = _write(
        tmp_path,
        "my_bad.cpp",
        "#include <iostream>\n"
        "int main(){ long long a,b; std::cin>>a>>b;"
        " std::cout<<(a==3 ? 0 : a+b)<<std::endl; }\n",
    )
    h2 = _Harness()
    assert h2.run(gen, my_bad, std, rounds=5)
    assert len(h2.failures) == 1
    assert h2.failures[0].index == 3
    assert h2.failures[0].my_output.strip() == "0"
    assert h2.failures[0].std_output.strip() == "7"


# ---- 面板 -----------------------------------------------------------------
def _fill_panel(panel: StressPanel, tmp_path, my_source=MY_GOOD_PY):
    gen, my, std = _programs(tmp_path, my_source)
    panel.gen_edit.setText(gen)
    panel.my_edit.setText(my)
    panel.std_edit.setText(std)
    return gen, my, std


def test_panel_all_pass(qapp, settings, tmp_path):
    panel = StressPanel(settings)
    _fill_panel(panel, tmp_path)
    panel.count_spin.setValue(3)
    finished = []
    panel.stress.all_finished.connect(lambda p, t: finished.append((p, t)))
    panel.start()
    assert wait_for(lambda: bool(finished), timeout_ms=60000)
    assert finished == [(3, 3)]
    assert "全部通过" in panel.status_label.text()
    assert panel.detail_frame.isHidden()


def test_panel_failure_shows_detail(qapp, settings, tmp_path):
    panel = StressPanel(settings)
    _fill_panel(panel, tmp_path, MY_BAD_PY)
    panel.count_spin.setValue(10)
    finished = []
    panel.stress.all_finished.connect(lambda p, t: finished.append((p, t)))
    panel.start()
    assert wait_for(lambda: bool(finished), timeout_ms=60000)
    assert "第 5 个测试点" in panel.status_label.text()
    assert not panel.detail_frame.isHidden()
    assert panel.input_view.toPlainText().split() == ["5", "6"]
    assert panel.my_view.toPlainText().strip() == "0"
    assert panel.std_view.toPlainText().strip() == "11"


def test_panel_requires_paths(qapp, settings):
    panel = StressPanel(settings)
    panel.start()
    assert "请先选择" in panel.status_label.text()


def test_panel_persists_paths(qapp, settings, tmp_path):
    panel = StressPanel(settings)
    gen, my, std = _fill_panel(panel, tmp_path)
    panel._persist()
    # 新面板恢复上次路径与数量
    panel2 = StressPanel(settings)
    assert panel2.my_edit.text() == my
    assert panel2.gen_edit.text() == gen
    assert panel2.std_edit.text() == std
    assert panel2.spj_edit.text() == ""


def test_panel_suggest_my_path_only_when_empty(qapp, settings, tmp_path):
    panel = StressPanel(settings)
    panel.suggest_my_path("a.cpp")
    assert panel.my_edit.text() == "a.cpp"
    panel.suggest_my_path("b.cpp")
    assert panel.my_edit.text() == "a.cpp"
