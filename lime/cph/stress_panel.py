# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""对拍面板：选择生成器/待测/标准程序（可选 SPJ），一键对拍并展示出错测试点。"""

from __future__ import annotations

import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings
from ..runner.runner import supported_extensions
from .stress import ROLE_LABELS, StressController, StressFailure
from .test_panel import _small_editor


class StressPanel(QWidget):
    """底部「对拍」标签页。"""

    #: 用户点击“使用当前文件”，由主窗口填入当前标签路径
    request_current_file = pyqtSignal()

    def __init__(self, settings: Settings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._failed_this_run = False

        self.stress = StressController(self)
        self.stress.started.connect(self._on_started)
        self.stress.compile_started.connect(self._on_compile_started)
        self.stress.compile_finished.connect(self._on_compile_finished)
        self.stress.progress.connect(self._on_progress)
        self.stress.test_failed.connect(self._on_test_failed)
        self.stress.all_finished.connect(self._on_all_finished)
        self.stress.stress_failed.connect(self._on_stress_failed)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # ---- 程序选择 ------------------------------------------------------
        form = QGridLayout()
        self.std_edit = QLineEdit()
        self.my_edit = QLineEdit()
        self.gen_edit = QLineEdit()
        self.spj_edit = QLineEdit()
        edits = [
            ("数据生成器", self.gen_edit, "gen_path"),
            ("待测程序", self.my_edit, "my_path"),
            ("标准程序", self.std_edit, "std_path"),
            ("Special Judge（可选）", self.spj_edit, "spj_path"),
        ]
        self._path_edits = {
            "gen_path": self.gen_edit,
            "my_path": self.my_edit,
            "std_path": self.std_edit,
            "spj_path": self.spj_edit,
        }
        for row, (label, edit, key) in enumerate(edits):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(edit, row, 1)
            browse = QPushButton("浏览…")
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            form.addWidget(browse, row, 2)
            edit.editingFinished.connect(self._persist)
        use_current = QPushButton("使用当前文件")
        use_current.clicked.connect(self.request_current_file.emit)
        form.addWidget(use_current, 1, 3)
        clear_spj = QPushButton("清空")
        clear_spj.clicked.connect(self._clear_spj)
        form.addWidget(clear_spj, 3, 3)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        # ---- 选项与操作 ----------------------------------------------------
        bar = QHBoxLayout()
        bar.addWidget(QLabel("测试点数"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000000)
        self.count_spin.setValue(1000)
        bar.addWidget(self.count_spin)
        bar.addWidget(QLabel("限时"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(5)
        bar.addWidget(self.timeout_spin)
        self.start_button = QPushButton("开始对拍 (F7)")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        bar.addWidget(self.start_button)
        bar.addWidget(self.stop_button)
        bar.addStretch(1)
        root.addLayout(bar)

        self.status_label = QLabel(
            "生成器向 stdout 输出数据，测试点编号（1 起）作为命令行参数传入；"
            "Special Judge 按 checker <输入> <待测输出> <标准输出> 调用，退出码 0 判通过。"
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.compile_label = QLabel("")
        self.compile_label.setWordWrap(True)
        self.compile_label.setStyleSheet("color: #f85149;")
        self.compile_label.hide()
        root.addWidget(self.compile_label)

        # ---- 出错测试点详情 -------------------------------------------------
        self.detail_frame = QFrame()
        self.detail_frame.setFrameShape(QFrame.Shape.StyledPanel)
        detail = QVBoxLayout(self.detail_frame)
        self.verdict_label = QLabel("")
        self.verdict_label.setStyleSheet("color: #f85149; font-weight: bold;")
        detail.addWidget(self.verdict_label)
        grid = QGridLayout()
        grid.addWidget(QLabel("输入"), 0, 0)
        grid.addWidget(QLabel("标准程序输出"), 0, 1)
        grid.addWidget(QLabel("待测程序输出"), 0, 2)
        self.input_view = _small_editor(read_only=True)
        self.std_view = _small_editor(read_only=True)
        self.my_view = _small_editor(read_only=True)
        grid.addWidget(self.input_view, 1, 0)
        grid.addWidget(self.std_view, 1, 1)
        grid.addWidget(self.my_view, 1, 2)
        detail.addLayout(grid)
        self.detail_frame.hide()
        root.addWidget(self.detail_frame)
        root.addStretch(1)

        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stress.stop)

        self._restore()

    # ---- 路径持久化 --------------------------------------------------------
    def _persist(self) -> None:
        if self.settings is None:
            return
        for key, edit in self._path_edits.items():
            self.settings.set(f"stress/{key}", edit.text().strip())
        self.settings.set("stress/count", self.count_spin.value())
        self.settings.set("stress/timeout", self.timeout_spin.value())

    def _restore(self) -> None:
        if self.settings is None:
            return
        for key, edit in self._path_edits.items():
            edit.setText(str(self.settings.get(f"stress/{key}", "")))
        self.count_spin.setValue(int(self.settings.get("stress/count", 1000)))
        self.timeout_spin.setValue(int(self.settings.get("stress/timeout", 5)))

    # ---- 外部接口 ----------------------------------------------------------
    def set_my_path(self, path: str | None) -> None:
        if path:
            self.my_edit.setText(path)
            self._persist()

    def suggest_my_path(self, path: str | None) -> None:
        """仅在待测程序为空时填入当前文件路径。"""
        if path and not self.my_edit.text().strip():
            self.set_my_path(path)

    # ---- 对拍 --------------------------------------------------------------
    def start(self) -> None:
        if self.stress.is_running():
            return
        gen = self.gen_edit.text().strip()
        my = self.my_edit.text().strip()
        std = self.std_edit.text().strip()
        spj = self.spj_edit.text().strip()
        if not gen or not my or not std:
            self._set_status(
                "请先选择数据生成器、待测程序和标准程序", color="#f85149"
            )
            return
        self._persist()
        self._failed_this_run = False
        self.detail_frame.hide()
        self.compile_label.hide()
        self._set_status("准备中…")
        self._set_running(True)
        ok = self.stress.start(
            gen,
            my,
            std,
            spj,
            rounds=self.count_spin.value(),
            timeout_ms=self.timeout_spin.value() * 1000,
        )
        if not ok:
            self._set_running(False)

    def _browse(self, edit: QLineEdit) -> None:
        current = edit.text().strip()
        start = (
            os.path.dirname(current)
            if current
            else (self.settings.last_dir if self.settings else "")
        ) or os.path.expanduser("~")
        filter_text = (
            "所有支持的文件 ("
            + " ".join(f"*{ext}" for ext in supported_extensions())
            + ");;所有文件 (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "选择程序源文件", start, filter_text)
        if path:
            edit.setText(path)
            self._persist()

    def _clear_spj(self) -> None:
        self.spj_edit.clear()
        self._persist()

    def _set_status(self, text: str, color: str = "") -> None:
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold;" if color else ""
        )
        self.status_label.setText(text)

    def _set_running(self, running: bool) -> None:
        for edit in self._path_edits.values():
            edit.setEnabled(not running)
        self.count_spin.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    # ---- 控制器信号 --------------------------------------------------------
    def _on_started(self) -> None:
        self._set_status("准备中…")

    def _on_compile_started(self, role: str) -> None:
        self._set_status(f"正在编译{ROLE_LABELS.get(role, role)}…")

    def _on_compile_finished(self, role: str, ok: bool, output: str) -> None:
        if not ok:
            label = ROLE_LABELS.get(role, role)
            self.compile_label.setText(f"{label}编译失败：\n" + output.strip()[-1500:])
            self.compile_label.show()
            self._set_status(f"{label}编译失败", color="#f85149")
            self._failed_this_run = True

    def _on_progress(self, done: int, total: int) -> None:
        self._set_status(f"对拍中… {done}/{total}")

    def _on_test_failed(self, failure: StressFailure) -> None:
        self._failed_this_run = True
        self.verdict_label.setText(
            f"第 {failure.index} 个测试点出错：{failure.message}"
        )
        self.input_view.setPlainText(failure.input)
        self.std_view.setPlainText(failure.std_output)
        self.my_view.setPlainText(failure.my_output)
        self.detail_frame.show()
        self._set_status(
            f"对拍失败：第 {failure.index} 个测试点出错", color="#f85149"
        )

    def _on_stress_failed(self, message: str) -> None:
        self._failed_this_run = True
        self._set_status(message, color="#f85149")

    def _on_all_finished(self, passed: int, total: int) -> None:
        self._set_running(False)
        if self._failed_this_run:
            return
        if passed == total:
            self._set_status(f"全部通过：{passed}/{total}", color="#3fb950")
        else:
            self._set_status(f"已停止：通过 {passed}/{total}", color="#d29922")
