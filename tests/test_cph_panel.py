# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""cph.test_panel：样例面板 UI 与端到端评测测试。"""

from __future__ import annotations

import glob
import json

from lime.cph.store import TestCase
from lime.cph.test_panel import CaseCard, CphPanel
from tests.conftest import wait_for


def test_case_card_emits_full_millisecond_id(qapp):
    # 毫秒时间戳 > 2^31，信号不能被 32 位 int 截断
    case_id = 1791028917086
    card = CaseCard(TestCase(id=case_id), 1)
    got: list = []
    card.run_requested.connect(lambda cid: got.append(cid))
    card.run_button.click()
    assert got == [case_id]


def _make_script(tmp_path):
    script = tmp_path / "ab.py"
    script.write_text(
        "a, b = map(int, input().split())\nprint(a + b)\n",
        encoding="utf-8",
    )
    return script


def test_bind_none_disables_actions(qapp):
    panel = CphPanel()
    panel.bind(None)
    assert panel.add_button.isEnabled() is False
    assert panel.run_all_button.isEnabled() is False
    assert "保存" in panel.hint_label.text()


def test_add_edit_delete_and_persist_cph_file(qapp, tmp_path):
    script = _make_script(tmp_path)
    panel = CphPanel()
    panel.bind(str(script))
    panel.add_case()
    assert len(panel._cards) == 1
    card = panel._cards[0]
    card.input_edit.setPlainText("20 22\n")
    card.expected_edit.setPlainText("42\n")
    panel._save_now()

    prob_files = glob.glob(str(tmp_path / ".cph" / ".ab.py_*.prob"))
    assert len(prob_files) == 1
    with open(prob_files[0], encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["tests"][0]["input"] == "20 22\n"
    assert data["tests"][0]["output"] == "42\n"
    assert data["srcPath"].endswith("ab.py")

    # 删除后样例为空，文件仍保留（CPH 不会主动删题目文件）
    panel._delete_case(card.case_id)
    assert panel._cards == []
    assert panel.hint_label.isHidden() is False


def test_run_all_end_to_end_updates_verdicts(qapp, tmp_path):
    script = _make_script(tmp_path)
    panel = CphPanel()
    panel.bind(str(script))
    panel.add_case()
    panel.add_case()
    panel._cards[0].input_edit.setPlainText("20 22")
    panel._cards[0].expected_edit.setPlainText("42")
    panel._cards[1].input_edit.setPlainText("1 1")
    panel._cards[1].expected_edit.setPlainText("9")
    # 触发 textChanged 后的脏数据本就在卡片里，run_all 会收集
    panel.run_all()
    assert wait_for(
        lambda: not panel.judge.is_running()
        and "评测完成" in panel.summary_label.text(),
        timeout_ms=30000,
    )
    assert "2/2" not in panel.summary_label.text()
    assert "1/2 通过" in panel.summary_label.text()
    assert "通过" in panel._cards[0].status_label.text()
    assert "答案错误" in panel._cards[1].status_label.text()
    assert panel._cards[1].actual_edit.toPlainText().strip() == "2"


def test_single_case_run_button(qapp, tmp_path):
    script = _make_script(tmp_path)
    panel = CphPanel()
    panel.bind(str(script))
    panel.add_case()
    card = panel._cards[0]
    card.input_edit.setPlainText("100 -60")
    card.expected_edit.setPlainText("40")
    card.run_button.click()
    assert wait_for(
        lambda: "通过" in card.status_label.text(), timeout_ms=30000
    )


def test_timeout_spinbox_persists_into_problem(qapp, tmp_path):
    script = _make_script(tmp_path)
    panel = CphPanel()
    panel.bind(str(script))
    panel.add_case()
    panel.timeout_spin.setValue(12)
    prob_files = glob.glob(str(tmp_path / ".cph" / ".ab.py_*.prob"))
    with open(prob_files[0], encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["timeLimit"] == 12000
