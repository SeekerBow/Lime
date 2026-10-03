# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""样例测试面板（CPH 风格）：管理并评测当前源文件的测试样例。"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings
from .judge import VERDICT_TEXT, CaseResult, JudgeController
from .store import (
    TestCase,
    load_problem,
    new_case_id,
    new_problem,
    save_problem,
)

_VERDICT_COLORS = {
    "accepted": "#3fb950",
    "wrong_answer": "#f85149",
    "timeout": "#d29922",
    "runtime_error": "#f85149",
    "failed_to_start": "#f85149",
}


def _small_editor(read_only: bool = False) -> QPlainTextEdit:
    edit = QPlainTextEdit()
    edit.setReadOnly(read_only)
    edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    edit.setFont(QFont("Consolas", 10))
    edit.setFixedHeight(96)
    return edit


class CaseCard(QFrame):
    """一条样例：输入/期望输出/实际输出 + 判定状态。"""

    run_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, case: TestCase, index: int, parent=None) -> None:
        super().__init__(parent)
        self.case_id = case.id
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)

        header = QHBoxLayout()
        self.title_label = QLabel(f"样例 {index}")
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        header.addWidget(self.title_label)
        self.status_label = QLabel("")
        header.addWidget(self.status_label, 1)
        self.run_button = QPushButton("运行")
        self.delete_button = QPushButton("删除")
        self.run_button.clicked.connect(lambda: self.run_requested.emit(self.case_id))
        self.delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self.case_id)
        )
        header.addWidget(self.run_button)
        header.addWidget(self.delete_button)
        root.addLayout(header)

        grid = QGridLayout()
        grid.addWidget(QLabel("输入"), 0, 0)
        grid.addWidget(QLabel("期望输出"), 0, 1)
        self.input_edit = _small_editor()
        self.expected_edit = _small_editor()
        self.input_edit.setPlainText(case.input)
        self.expected_edit.setPlainText(case.output)
        grid.addWidget(self.input_edit, 1, 0)
        grid.addWidget(self.expected_edit, 1, 1)
        root.addLayout(grid)

        self.actual_label = QLabel("实际输出")
        self.actual_edit = _small_editor(read_only=True)
        root.addWidget(self.actual_label)
        root.addWidget(self.actual_edit)
        self.set_actual_visible(False)

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"样例 {index}")

    def set_actual_visible(self, visible: bool) -> None:
        self.actual_label.setVisible(visible)
        self.actual_edit.setVisible(visible)

    def set_running(self) -> None:
        self.status_label.setText("运行中…")
        self.status_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        self.run_button.setEnabled(False)

    def set_result(self, result: CaseResult) -> None:
        self.run_button.setEnabled(True)
        self.actual_edit.setPlainText(result.actual)
        self.set_actual_visible(True)
        color = _VERDICT_COLORS.get(result.verdict, "#8b949e")
        text = VERDICT_TEXT.get(result.verdict, result.verdict)
        extra = ""
        if result.verdict == "accepted":
            extra = f"（{result.elapsed_ms} ms）"
        elif result.whitespace_only:
            extra = "（仅空白/换行差异）"
        elif result.message:
            extra = f"（{result.message}）"
        self.status_label.setText(f"● {text}{extra}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def clear_result(self) -> None:
        self.status_label.setText("")
        self.status_label.setStyleSheet("")
        self.run_button.setEnabled(True)
        self.actual_edit.clear()
        self.set_actual_visible(False)

    def set_controls_enabled(self, enabled: bool) -> None:
        if self.status_label.text() != "运行中…":
            self.run_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.input_edit.setEnabled(enabled)
        self.expected_edit.setEnabled(enabled)

    def to_case(self) -> TestCase:
        return TestCase(
            id=self.case_id,
            input=self.input_edit.toPlainText(),
            output=self.expected_edit.toPlainText(),
        )


class CphPanel(QWidget):
    """当前源文件的样例列表面板。"""

    request_save_current = pyqtSignal()

    def __init__(self, settings: Settings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._src_path: str | None = None
        self._problem = None
        self._cards: list[CaseCard] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_now)

        self.judge = JudgeController(self)
        self.judge.compile_started.connect(self._on_compile_started)
        self.judge.compile_finished.connect(self._on_compile_finished)
        self.judge.case_started.connect(self._on_case_started)
        self.judge.case_finished.connect(self._on_case_finished)
        self.judge.all_finished.connect(self._on_all_finished)
        self.judge.judge_failed.connect(self._on_judge_failed)
        self._running_single_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.add_button = QPushButton("添加样例")
        self.run_all_button = QPushButton("全部运行 (F6)")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        bar.addWidget(self.add_button)
        bar.addWidget(self.run_all_button)
        bar.addWidget(self.stop_button)
        bar.addWidget(QLabel("限时"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(5)
        bar.addWidget(self.timeout_spin)
        bar.addStretch(1)
        root.addLayout(bar)

        self.summary_label = QLabel("")
        root.addWidget(self.summary_label)
        self.compile_label = QLabel("")
        self.compile_label.setWordWrap(True)
        self.compile_label.setStyleSheet("color: #f85149;")
        self.compile_label.hide()
        root.addWidget(self.compile_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.hint_label = QLabel(
            "当前文件还没有样例，点击“添加样例”手动录入。\n"
            "样例保存在源文件旁的 .cph 目录，格式与 VSCode 插件 CPH 兼容。"
        )
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint_label)

        self.add_button.clicked.connect(self.add_case)
        self.run_all_button.clicked.connect(self.run_all)
        self.stop_button.clicked.connect(self.judge.stop)
        self.timeout_spin.valueChanged.connect(self._on_timeout_changed)
        self._set_running_controls(False)

    # ---- 文件绑定 --------------------------------------------------------
    def bind(self, src_path: str | None) -> None:
        """切换到指定源文件；未保存的文档传 None。"""
        self._save_now()
        self._src_path = os.path.abspath(src_path) if src_path else None
        if self._src_path is None:
            self._problem = None
        else:
            self._problem = load_problem(self._src_path) or new_problem(
                self._src_path
            )
        self.timeout_spin.blockSignals(True)
        self.timeout_spin.setValue(
            max(1, (self._problem.timeLimit if self._problem else 5000) // 1000)
        )
        self.timeout_spin.blockSignals(False)
        self._rebuild_cards()

    def current_path(self) -> str | None:
        return self._src_path

    # ---- 样例增删 --------------------------------------------------------
    def add_case(self) -> None:
        if self._problem is None:
            return
        case = TestCase(id=new_case_id())
        self._problem.tests.append(case)
        card = self._create_card(case, len(self._cards) + 1)
        self._cards.append(card)
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._refresh_indices()
        self._update_hint()
        card.input_edit.setFocus()
        self._save_now()

    def _delete_case(self, case_id: int) -> None:
        if self._problem is None:
            return
        self._problem.tests = [c for c in self._problem.tests if c.id != case_id]
        for card in list(self._cards):
            if card.case_id == case_id:
                self._cards.remove(card)
                self.cards_layout.removeWidget(card)
                card.deleteLater()
        self._refresh_indices()
        self._update_hint()
        self._save_now()

    def _rebuild_cards(self) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards = []
        if self._problem is not None:
            for index, case in enumerate(self._problem.tests, start=1):
                card = self._create_card(case, index)
                self._cards.append(card)
                self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._update_hint()

    def _create_card(self, case: TestCase, index: int) -> CaseCard:
        card = CaseCard(case, index)
        card.run_requested.connect(self._run_single)
        card.delete_requested.connect(self._delete_case)
        card.input_edit.textChanged.connect(self._schedule_save)
        card.expected_edit.textChanged.connect(self._schedule_save)
        return card

    def _refresh_indices(self) -> None:
        for index, card in enumerate(self._cards, start=1):
            card.set_index(index)

    def _update_hint(self) -> None:
        has_problem = self._problem is not None
        self.hint_label.setVisible(has_problem and not self._cards)
        self.add_button.setEnabled(has_problem)
        self.run_all_button.setEnabled(has_problem)
        self.timeout_spin.setEnabled(has_problem)
        if not has_problem:
            self.hint_label.setText("请先保存文件，再为它添加测试样例。")
            self.hint_label.setVisible(True)

    # ---- 持久化 ----------------------------------------------------------
    def _collect_edits(self) -> None:
        if self._problem is None:
            return
        self._problem.tests = [card.to_case() for card in self._cards]

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        self._save_timer.stop()
        if self._problem is None:
            return
        self._collect_edits()
        if self._problem.tests:
            save_problem(self._problem)

    def _on_timeout_changed(self, seconds: int) -> None:
        if self._problem is not None:
            self._problem.timeLimit = seconds * 1000
            self._save_now()

    # ---- 评测 ------------------------------------------------------------
    def run_all(self) -> None:
        if not self._can_start():
            return
        cases = [card.to_case() for card in self._cards]
        self._start(cases)

    def _run_single(self, case_id: int) -> None:
        if not self._can_start():
            return
        cases = [c for c in (card.to_case() for card in self._cards) if c.id == case_id]
        self._running_single_id = case_id
        self._start(cases)

    def _can_start(self) -> bool:
        if self._problem is None or self._src_path is None:
            return False
        if self.judge.is_running():
            return False
        if not self._cards:
            self.summary_label.setText("还没有样例，先添加一条吧。")
            return False
        self._save_now()
        # 源文件可能有未保存改动，交给主窗口先保存（CPH 同样如此）
        self.request_save_current.emit()
        return True

    def _start(self, cases) -> None:
        self.compile_label.hide()
        for card in self._cards:
            card.clear_result()
        self.summary_label.setText("评测中…")
        self._set_running_controls(True)
        ok = self.judge.run_cases(
            self._src_path, cases, self.timeout_spin.value() * 1000
        )
        if not ok:
            self._set_running_controls(False)

    def _set_running_controls(self, running: bool) -> None:
        self.add_button.setEnabled(not running and self._problem is not None)
        self.run_all_button.setEnabled(not running and self._problem is not None)
        self.stop_button.setEnabled(running)
        self.timeout_spin.setEnabled(not running and self._problem is not None)
        for card in self._cards:
            card.set_controls_enabled(not running)

    def _on_compile_started(self) -> None:
        self.summary_label.setText("正在编译…")

    def _on_compile_finished(self, ok: bool, output: str) -> None:
        if not ok:
            self.compile_label.setText("编译失败：\n" + output.strip()[-1500:])
            self.compile_label.show()
            self.summary_label.setText("编译失败")

    def _on_case_started(self, case_id: int) -> None:
        card = self._card(case_id)
        if card is not None:
            card.set_running()

    def _on_case_finished(self, result: CaseResult) -> None:
        card = self._card(result.case_id)
        if card is not None:
            card.set_result(result)

    def _on_all_finished(self, results: list) -> None:
        self._running_single_id = None
        self._set_running_controls(False)
        if results:
            accepted = sum(r.verdict == "accepted" for r in results)
            total = len(results)
            color = "#3fb950" if accepted == total else "#f85149"
            self.summary_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            self.summary_label.setText(f"评测完成：{accepted}/{total} 通过")
        elif self.compile_label.isHidden():
            self.summary_label.setText("")
            self.summary_label.setStyleSheet("")

    def _on_judge_failed(self, message: str) -> None:
        self._set_running_controls(False)
        self.summary_label.setStyleSheet("color: #f85149;")
        self.summary_label.setText(message)

    def _card(self, case_id: int) -> CaseCard | None:
        for card in self._cards:
            if card.case_id == case_id:
                return card
        return None
