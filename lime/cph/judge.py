# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""样例评测引擎：编译一次，逐样例运行程序并判定。

- 解释型语言（Python/Node/…）每个样例直接启动解释器；
- 编译型语言（C/C++/Java）先统一编译到临时目录，成功后复用产物；
- 每个样例独立进程：注入 stdin、收集 stdout/stderr、限时、判定。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from ..runner.runner import (
    COMPILED_RUNNERS,
    RUNNERS,
    cleanup_artifacts,
)
from ..terminal.terminal import decode_process_bytes, encode_process_input
from .checker import check_answer, whitespace_only_difference
from .store import TestCase

IS_WINDOWS = sys.platform.startswith("win")

VERDICT_ACCEPTED = "accepted"
VERDICT_WRONG = "wrong_answer"
VERDICT_TIMEOUT = "timeout"
VERDICT_RUNTIME = "runtime_error"
VERDICT_FAILED_START = "failed_to_start"

VERDICT_TEXT = {
    VERDICT_ACCEPTED: "通过",
    VERDICT_WRONG: "答案错误",
    VERDICT_TIMEOUT: "超时",
    VERDICT_RUNTIME: "运行错误",
    VERDICT_FAILED_START: "无法启动",
}


@dataclass
class CaseResult:
    """单条样例的评测结果。"""

    case_id: int
    verdict: str
    expected: str = ""
    actual: str = ""
    elapsed_ms: int = 0
    message: str = ""
    whitespace_only: bool = False


def _write_compile_batch(src_path: str, language: str, output_dir: str) -> str:
    """生成只负责编译的临时 .bat（-static、引号、错误即退出）。"""
    source = os.path.basename(src_path)
    stem = os.path.splitext(source)[0]
    if language == "java":
        lines = [
            f'javac -encoding UTF-8 -d "{output_dir}" "{source}"',
            "if errorlevel 1 exit /b 1",
        ]
    else:
        compiler = "gcc" if language == "c" else "g++"
        exe = os.path.join(output_dir, stem + ".exe")
        lines = [
            f'{compiler} -static "{source}" -o "{exe}"',
            "if errorlevel 1 exit /b 1",
        ]
    fd, batch_path = tempfile.mkstemp(prefix="lime_cph_build_", suffix=".bat")
    with os.fdopen(fd, "w", encoding="mbcs", errors="replace", newline="") as fh:
        fh.write("@echo off\r\n")
        fh.write("\r\n".join(lines))
        fh.write("\r\n")
    return batch_path


def _compile_command(src_path: str, language: str, output_dir: str) -> tuple[list[str], list[str]]:
    """返回 (编译命令, 需清理的临时文件)。"""
    if IS_WINDOWS:
        batch = _write_compile_batch(src_path, language, output_dir)
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", batch], [batch, output_dir]
    source = os.path.basename(src_path)
    if language == "java":
        line = f'javac -encoding UTF-8 -d "{output_dir}" "{source}"'
    else:
        compiler = "gcc" if language == "c" else "g++"
        exe = os.path.join(output_dir, os.path.splitext(source)[0])
        line = f'{compiler} "{source}" -o "{exe}"'
    return ["/bin/sh", "-c", line], [output_dir]


def _run_command(src_path: str, language: str, output_dir: str) -> list[str]:
    """编译成功后，每个样例实际运行的命令。"""
    stem = os.path.splitext(os.path.basename(src_path))[0]
    if language == "java":
        return ["java", "-cp", output_dir, stem]
    if IS_WINDOWS:
        return [os.path.join(output_dir, stem + ".exe")]
    return [os.path.join(output_dir, stem)]


class JudgeController(QObject):
    """串行评测一组样例。"""

    compile_started = pyqtSignal()
    #: ok, 编译器输出
    compile_finished = pyqtSignal(bool, str)
    case_started = pyqtSignal(object)
    case_finished = pyqtSignal(object)
    all_finished = pyqtSignal(list)
    #: 不支持的文件类型等致命错误
    judge_failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._queue: list[TestCase] = []
        self._current: TestCase | None = None
        self._run_cmd: list[str] = []
        self._cwd = ""
        self._timeout_ms = 5000
        self._buffer = bytearray()
        self._started_at = 0.0
        self._timed_out = False
        self._phase = ""  # "compile" | "run"
        self._results: list[CaseResult] = []
        self._cleanup: list[str] = []
        self._start_failed = False

    def is_running(self) -> bool:
        return self._phase != ""

    def stop(self) -> None:
        if self._timeout_timer.isActive():
            self._timeout_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self._finish_all()

    # ---- 入口 ------------------------------------------------------------
    def run_cases(
        self,
        src_path: str,
        cases: list[TestCase],
        timeout_ms: int = 5000,
    ) -> bool:
        """开始评测；文件类型不支持或已有任务时返回 False。"""
        if self.is_running():
            return False
        src_path = os.path.abspath(src_path)
        ext = os.path.splitext(src_path)[1].lower()
        self._cwd = os.path.dirname(src_path)
        self._timeout_ms = max(100, int(timeout_ms))
        self._results = []
        self._cleanup = []

        if ext in COMPILED_RUNNERS:
            output_dir = tempfile.mkdtemp(prefix="lime_cph_build_")
            command, self._cleanup = _compile_command(
                src_path, COMPILED_RUNNERS[ext], output_dir
            )
            self._run_cmd = _run_command(
                src_path, COMPILED_RUNNERS[ext], output_dir
            )
            self._queue = list(cases)
            self._phase = "compile"
            self.compile_started.emit()
            self.process.setWorkingDirectory(self._cwd)
            self._buffer = bytearray()
            self.process.start(command[0], command[1:])
            return True

        builder = RUNNERS.get(ext)
        if builder is None:
            self.judge_failed.emit("该文件类型不支持样例评测")
            return False
        self._run_cmd = builder(src_path)
        self._queue = list(cases)
        # 解释型没有编译阶段，直接进入样例运行
        QTimer.singleShot(0, self._next_case)
        self._phase = "run"
        return True

    # ---- 内部状态机 -------------------------------------------------------
    def _next_case(self) -> None:
        if not self._queue:
            self._finish_all()
            return
        self._current = self._queue.pop(0)
        self._buffer = bytearray()
        self._timed_out = False
        self._start_failed = False
        self._started_at = time.monotonic()
        self.case_started.emit(self._current.id)
        self.process.setWorkingDirectory(self._cwd)
        self.process.start(self._run_cmd[0], self._run_cmd[1:])

    def _read_output(self) -> None:
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))

    def _on_started(self) -> None:
        # 仅在样例运行阶段注入 stdin；编译阶段不干预
        if self._phase != "run" or self._current is None:
            return
        data = encode_process_input(self._current.input)
        if data:
            self.process.write(data)
        # 发送 EOF，保证 read-all 型程序能结束
        self.process.closeWriteChannel()
        self._timeout_timer.start(self._timeout_ms)

    def _on_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._start_failed = True

    def _on_timeout(self) -> None:
        self._timed_out = True
        self.process.kill()

    def _on_finished(self, code: int, status) -> None:
        if self._timeout_timer.isActive():
            self._timeout_timer.stop()
        output = decode_process_bytes(bytes(self._buffer))
        elapsed = int((time.monotonic() - self._started_at) * 1000)

        if self._phase == "compile":
            ok = code == 0 and status == QProcess.ExitStatus.NormalExit
            self.compile_finished.emit(ok, output)
            if not ok:
                self._abort_after_failed_compile()
                return
            self._phase = "run"
            self._next_case()
            return

        # run 阶段
        assert self._current is not None
        case = self._current
        if self._start_failed:
            verdict, message = (
                VERDICT_FAILED_START,
                "无法启动程序/解释器，请确认它已安装并在 PATH 中",
            )
        elif self._timed_out:
            verdict, message = (
                VERDICT_TIMEOUT,
                f"超过 {self._timeout_ms} ms 被终止",
            )
        elif status == QProcess.ExitStatus.CrashExit or code != 0:
            verdict, message = VERDICT_RUNTIME, f"进程异常退出（退出码 {code}）"
        elif check_answer(case.output, output):
            verdict, message = VERDICT_ACCEPTED, ""
        else:
            verdict = VERDICT_WRONG
            message = "输出与期望不一致"
        result = CaseResult(
            case_id=case.id,
            verdict=verdict,
            expected=case.output,
            actual=output,
            elapsed_ms=elapsed,
            message=message,
            whitespace_only=(
                verdict == VERDICT_WRONG
                and whitespace_only_difference(case.output, output)
            ),
        )
        self._results.append(result)
        self.case_finished.emit(result)
        self._current = None
        self._next_case()

    def _abort_after_failed_compile(self) -> None:
        cleanup_artifacts(self._cleanup)
        self._cleanup = []
        self._phase = ""
        self.all_finished.emit([])

    def _finish_all(self) -> None:
        cleanup_artifacts(self._cleanup)
        self._cleanup = []
        results = list(self._results)
        self._results = []
        self._queue = []
        self._current = None
        self._phase = ""
        self.all_finished.emit(results)
