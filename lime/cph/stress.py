# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""一键对拍引擎：生成数据 → 运行待测/标准程序 → 比对，出错即停。

程序角色（均为源码文件；编译型先各自编译一次，解释型直接运行）：

- 数据生成器 gen：以测试点编号（1 起）作为命令行参数，向 stdout 输出数据；
- 待测程序 my / 标准程序 std：从 stdin 读数据，向 stdout 写答案；
- 可选 Special Judge：按 testlib 习惯以
  ``checker <输入文件> <待测输出文件> <标准输出文件>`` 调用，
  退出码 0 判通过，非 0 判不通过。

每轮串行执行 gen → my → std → (checker)；比对失败或待测程序异常时
立即停止并发出出错测试点的完整信息。每次启动恰好以一次
:data:`all_finished` 信号结束（含编译失败、中途停止等所有路径）。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from ..runner.runner import COMPILED_RUNNERS, RUNNERS, cleanup_artifacts
from ..terminal.terminal import decode_process_bytes, encode_process_input
from .checker import check_answer
from .judge import _compile_command, _run_command

#: 程序角色 -> 中文名
ROLE_LABELS = {
    "gen": "数据生成器",
    "my": "待测程序",
    "std": "标准程序",
    "checker": "Special Judge",
}


@dataclass
class StressFailure:
    """出错测试点的完整信息。"""

    index: int
    input: str
    my_output: str
    std_output: str
    message: str


class StressController(QObject):
    """串行对拍控制器。"""

    started = pyqtSignal()
    #: 正在编译的程序角色
    compile_started = pyqtSignal(str)
    #: 程序角色, 是否成功, 编译器输出
    compile_finished = pyqtSignal(str, bool, str)
    #: 已完成轮数, 总轮数
    progress = pyqtSignal(int, int)
    #: StressFailure（出错即停）
    test_failed = pyqtSignal(object)
    #: 通过数, 总轮数 —— 每次运行恰好发出一次
    all_finished = pyqtSignal(int, int)
    #: 致命错误（路径无效 / 类型不支持 / 生成器等基础设施异常）
    stress_failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._run_cmds: dict[str, list[str]] = {}
        self._cwds: dict[str, str] = {}
        self._compile_queue: list[tuple[str, list[str], str]] = []
        self._compile_role = ""
        self._cleanup: list[str] = []

        self._phase = ""  # "" | "compile" | "gen" | "my" | "std" | "checker"
        self._round = 0
        self._total = 1000
        self._passed = 0
        self._timeout_ms = 5000
        self._buffer = bytearray()
        self._timed_out = False
        self._start_failed = False
        self._stdin_data = b""

        self._input = b""
        self._my_out = b""
        self._std_out = b""
        self._spj_dir = ""

    # ---- 公共接口 ----------------------------------------------------------
    def is_running(self) -> bool:
        return self._phase != ""

    def stop(self) -> None:
        if not self.is_running():
            return
        if self._timeout_timer.isActive():
            self._timeout_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self._finish()

    def start(
        self,
        gen_path: str,
        my_path: str,
        std_path: str,
        checker_path: str = "",
        rounds: int = 1000,
        timeout_ms: int = 5000,
    ) -> bool:
        """开始对拍；参数异常或已有任务时返回 False。"""
        if self.is_running():
            return False
        paths = {"gen": gen_path, "my": my_path, "std": std_path}
        if checker_path:
            paths["checker"] = checker_path
        for role, path in paths.items():
            if not path or not os.path.isfile(path):
                self.stress_failed.emit(
                    f"{ROLE_LABELS[role]}路径无效：{path or '（空）'}"
                )
                return False
            ext = os.path.splitext(path)[1].lower()
            if ext not in COMPILED_RUNNERS and ext not in RUNNERS:
                self.stress_failed.emit(
                    f"{ROLE_LABELS[role]}文件类型不支持：{path}"
                )
                return False

        self._total = max(1, int(rounds))
        self._timeout_ms = max(100, int(timeout_ms))
        self._round = 0
        self._passed = 0
        self._cleanup = []
        self._run_cmds = {}
        self._cwds = {}
        self._compile_queue = []
        self._spj_dir = ""

        for role, path in paths.items():
            path = os.path.abspath(path)
            ext = os.path.splitext(path)[1].lower()
            self._cwds[role] = os.path.dirname(path)
            language = COMPILED_RUNNERS.get(ext)
            if language is None:
                self._run_cmds[role] = RUNNERS[ext](path)
                continue
            output_dir = tempfile.mkdtemp(prefix=f"lime_stress_{role}_")
            compile_cmd, cleanup = _compile_command(path, language, output_dir)
            self._cleanup.extend(cleanup)
            self._run_cmds[role] = _run_command(path, language, output_dir)
            self._compile_queue.append((role, compile_cmd, self._cwds[role]))

        if "checker" in self._run_cmds:
            self._spj_dir = tempfile.mkdtemp(prefix="lime_stress_spj_")
            self._cleanup.append(self._spj_dir)

        self.started.emit()
        if self._compile_queue:
            self._phase = "compile"
            self._start_next_compile()
        else:
            self._phase = "gen"
            QTimer.singleShot(0, self._next_round)
        return True

    # ---- 内部流程 ----------------------------------------------------------
    def _start_next_compile(self) -> None:
        role, cmd, cwd = self._compile_queue.pop(0)
        self._compile_role = role
        self._buffer = bytearray()
        self._start_failed = False
        self.compile_started.emit(role)
        self.process.setWorkingDirectory(cwd)
        self.process.start(cmd[0], cmd[1:])

    def _next_round(self) -> None:
        self._round += 1
        self._input = b""
        self._my_out = b""
        self._std_out = b""
        self._start_program("gen", [str(self._round)])

    def _start_program(
        self, phase: str, extra_args: list[str] | None = None
    ) -> None:
        self._phase = phase
        self._buffer = bytearray()
        self._timed_out = False
        self._start_failed = False
        self._stdin_data = self._input if phase in ("my", "std") else b""
        cmd = list(self._run_cmds[phase]) + list(extra_args or [])
        self.process.setWorkingDirectory(self._cwds[phase])
        self.process.start(cmd[0], cmd[1:])

    def _run_checker(self) -> None:
        assert self._spj_dir
        input_file = os.path.join(self._spj_dir, "input.txt")
        my_file = os.path.join(self._spj_dir, "my_output.txt")
        std_file = os.path.join(self._spj_dir, "std_output.txt")
        try:
            with open(input_file, "wb") as fh:
                fh.write(self._input)
            with open(my_file, "wb") as fh:
                fh.write(self._my_out)
            with open(std_file, "wb") as fh:
                fh.write(self._std_out)
        except OSError as exc:
            self._fatal(f"写入 Special Judge 临时文件失败：{exc}")
            return
        self._start_program("checker", [input_file, my_file, std_file])

    def _pass_round(self) -> None:
        self._passed += 1
        self.progress.emit(self._passed, self._total)
        if self._passed >= self._total:
            self._finish()
        else:
            self._next_round()

    def _fail_test(self, message: str, my_output: bytes | None = None) -> None:
        if my_output is None:
            my_output = self._my_out
        failure = StressFailure(
            index=self._round,
            input=decode_process_bytes(bytes(self._input)),
            my_output=decode_process_bytes(bytes(my_output)),
            std_output=decode_process_bytes(bytes(self._std_out)),
            message=message,
        )
        self.test_failed.emit(failure)
        self._finish()

    def _fatal(self, message: str) -> None:
        """基础设施（生成器/标准程序/SPJ）异常：无法继续对拍。"""
        self.stress_failed.emit(message)
        self._finish()

    def _run_problem(self, code: int, status) -> str:
        """子进程异常的描述；正常返回空串。"""
        if self._start_failed:
            return "无法启动，请确认解释器/编译器已安装并在 PATH 中"
        if self._timed_out:
            return f"超过 {self._timeout_ms} ms 被终止"
        if status == QProcess.ExitStatus.CrashExit or code != 0:
            return f"异常退出（退出码 {code}）"
        return ""

    def _finish(self) -> None:
        self._phase = ""
        self._compile_queue = []
        cleanup_artifacts(self._cleanup)
        self._cleanup = []
        self.all_finished.emit(self._passed, self._total)

    # ---- QProcess 槽 -------------------------------------------------------
    def _read_output(self) -> None:
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))

    def _on_started(self) -> None:
        if self._phase not in ("gen", "my", "std", "checker"):
            return
        if self._stdin_data:
            self.process.write(self._stdin_data)
        self._stdin_data = b""
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
        phase = self._phase
        if not phase:
            # stop() 已收尾，忽略 kill 触发的 finished
            return
        if self._timeout_timer.isActive():
            self._timeout_timer.stop()
        output = bytes(self._buffer)

        if phase == "compile":
            ok = (
                code == 0
                and status == QProcess.ExitStatus.NormalExit
                and not self._start_failed
            )
            text = decode_process_bytes(output)
            self.compile_finished.emit(self._compile_role, ok, text)
            if not ok:
                self._finish()
                return
            if self._compile_queue:
                self._start_next_compile()
            else:
                self._phase = "gen"
                self._next_round()
            return

        if phase == "gen":
            problem = self._run_problem(code, status)
            if problem:
                self._fatal(f"数据生成器{problem}")
                return
            self._input = output
            self._start_program("my")
            return

        if phase == "my":
            problem = self._run_problem(code, status)
            if problem:
                self._fail_test(f"待测程序{problem}", my_output=output)
                return
            self._my_out = output
            self._start_program("std")
            return

        if phase == "std":
            problem = self._run_problem(code, status)
            if problem:
                self._fatal(f"标准程序{problem}")
                return
            self._std_out = output
            if "checker" in self._run_cmds:
                self._run_checker()
            elif check_answer(
                decode_process_bytes(bytes(self._std_out)),
                decode_process_bytes(bytes(self._my_out)),
            ):
                self._pass_round()
            else:
                self._fail_test("输出与标准程序不一致")
            return

        # checker
        problem = self._run_problem(code, status)
        if problem:
            self._fatal(f"Special Judge{problem}")
            return
        if code == 0:
            self._pass_round()
        else:
            self._fail_test(f"Special Judge 判定不通过（退出码 {code}）")
