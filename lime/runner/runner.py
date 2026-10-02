"""脚本运行器：把文件扩展名映射为系统命令并用 :class:`QProcess` 执行。

- 解释型语言（Python/Node/…）直接一条命令启动；
- 编译型语言（Java/C/C++）先编译到临时目录再运行产物：
  * POSIX 用 ``sh -c "编译 && 运行"``；
  * Windows 生成临时 ``.bat`` 执行，避免 ``cmd /c`` 复合命令的
    嵌套引号/转义问题（路径可能含空格或非 ASCII 字符）。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

IS_WINDOWS = sys.platform.startswith("win")

#: 扩展名 -> 解释型命令行生成函数
CommandBuilder = Callable[[str], list[str]]


def _python_command(path: str) -> list[str]:
    # 优先使用当前解释器，保证与编辑器同一环境
    return [sys.executable, path]


def _cmd_command(path: str) -> list[str]:
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    return [comspec, "/c", path]


def _powershell_command(path: str) -> list[str]:
    return ["powershell", "-ExecutionPolicy", "Bypass", "-File", path]


#: 解释型（直接运行）扩展名表
RUNNERS: dict[str, CommandBuilder] = {
    ".py": _python_command,
    ".js": lambda p: ["node", p],
    ".mjs": lambda p: ["node", p],
    ".bat": _cmd_command,
    ".cmd": _cmd_command,
    ".ps1": _powershell_command,
    ".sh": lambda p: ["bash", p],
    ".rb": lambda p: ["ruby", p],
    ".go": lambda p: ["go", "run", p],
}

#: 编译型扩展名 -> 语言键
COMPILED_RUNNERS: dict[str, str] = {
    ".java": "java",
    ".c": "c",
    ".cpp": "c++",
    ".cc": "c++",
    ".cxx": "c++",
}


@dataclass
class RunPlan:
    """一次运行的完整计划。"""

    command: list[str]
    cwd: str
    display: str
    #: 运行结束后需要删除的临时文件/目录
    cleanup: list[str] = field(default_factory=list)


def build_command(path: str) -> Optional[list[str]]:
    """根据扩展名返回命令及参数列表，不支持时返回 ``None``。

    解释型语言返回直接可执行的命令；编译型语言返回包装好的
    shell/批处理命令（会创建临时构建目录）。
    """
    plan = build_run_plan(path)
    return plan.command if plan is not None else None


def supported_extensions() -> tuple[str, ...]:
    return tuple(RUNNERS) + tuple(COMPILED_RUNNERS)


# --------------------------------------------------------------------------
# 编译型语言支持
# --------------------------------------------------------------------------
def compiled_shell_line(path: str, language: str, output_dir: str) -> str:
    """返回 POSIX 下的 ``编译 && 运行`` 复合命令（纯函数，便于测试）。"""
    source = os.path.basename(path)
    stem = os.path.splitext(source)[0]
    if language == "java":
        return (
            f'javac -encoding UTF-8 -d "{output_dir}" "{source}" '
            f'&& java -cp "{output_dir}" "{stem}"'
        )
    if language in ("c", "c++"):
        compiler = "gcc" if language == "c" else "g++"
        exe = os.path.join(output_dir, stem)
        return f'{compiler} "{source}" -o "{exe}" && "{exe}"'
    raise ValueError(f"不支持的编译语言：{language}")


def _write_windows_batch(path: str, language: str, output_dir: str) -> str:
    """生成执行 编译+运行 的临时 .bat，返回其路径。

    批处理用系统 ANSI 代码页写出，避免非 ASCII 路径乱码；
    所有路径加引号；编译失败立即返回非零退出码。
    """
    source = os.path.basename(path)
    stem = os.path.splitext(source)[0]
    if language == "java":
        lines = [
            f'javac -encoding UTF-8 -d "{output_dir}" "{source}"',
            "if errorlevel 1 exit /b 1",
            f'java -cp "{output_dir}" "{stem}"',
            "exit /b %errorlevel%",
        ]
    elif language in ("c", "c++"):
        compiler = "gcc" if language == "c" else "g++"
        exe = os.path.join(output_dir, stem + ".exe")
        # -static：MinGW 产物不依赖 libgcc/libstdc++/winpthread DLL
        lines = [
            f'{compiler} -static "{source}" -o "{exe}"',
            "if errorlevel 1 exit /b 1",
            f'"{exe}"',
            "exit /b %errorlevel%",
        ]
    else:
        raise ValueError(f"不支持的编译语言：{language}")

    fd, batch_path = tempfile.mkstemp(prefix="lime_build_", suffix=".bat")
    # newline="" 防止文本模式改写换行；mbcs 匹配 cmd 默认代码页
    with os.fdopen(fd, "w", encoding="mbcs", errors="replace", newline="") as fh:
        fh.write("@echo off\r\n")
        fh.write("\r\n".join(lines))
        fh.write("\r\n")
    return batch_path


def _display_line(path: str, language: str, output_dir: str) -> str:
    source = os.path.basename(path)
    stem = os.path.splitext(source)[0]
    if language == "java":
        return f"javac {source} && java {stem}"
    compiler = "gcc" if language == "c" else "g++"
    exe = os.path.join(output_dir, stem + (".exe" if IS_WINDOWS else ""))
    return f"{compiler} {source} && {exe}"


def build_run_plan(path: str) -> Optional[RunPlan]:
    """为文件构造完整运行计划；不支持的扩展名返回 ``None``。"""
    ext = os.path.splitext(path)[1].lower()

    interpreter = RUNNERS.get(ext)
    if interpreter is not None:
        cwd = os.path.dirname(os.path.abspath(path))
        return RunPlan(interpreter(path), cwd, " ".join(interpreter(path)))

    language = COMPILED_RUNNERS.get(ext)
    if language is None:
        return None

    source_dir = os.path.dirname(os.path.abspath(path))
    output_dir = tempfile.mkdtemp(prefix="lime_build_")
    display = _display_line(path, language, output_dir)

    if IS_WINDOWS:
        batch = _write_windows_batch(path, language, output_dir)
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        # bat 路径作为整体参数（含空格时由 Qt 加一对引号），
        # cmd 只会剥除这一层引号，不涉及嵌套转义。
        return RunPlan(
            command=[comspec, "/c", batch],
            cwd=source_dir,
            display=display,
            cleanup=[batch, output_dir],
        )

    line = compiled_shell_line(path, language, output_dir)
    return RunPlan(
        command=["/bin/sh", "-c", line],
        cwd=source_dir,
        display=display,
        cleanup=[output_dir],
    )


def cleanup_artifacts(paths) -> None:
    """删除运行产生的临时文件与目录，容忍占用/权限错误。"""
    for item in paths:
        try:
            if os.path.isdir(item):
                shutil.rmtree(item, ignore_errors=True)
            elif os.path.exists(item):
                os.remove(item)
        except OSError:
            pass


class CodeRunner(QObject):
    """异步运行脚本，合并 stdout/stderr，以信号通知结果。"""

    started = pyqtSignal(str)
    output_emitted = pyqtSignal(str)
    #: exit_code, status("normal" | "crashed" | "failed_to_start")
    run_finished = pyqtSignal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self._current_path: Optional[str] = None
        self._cleanup: list[str] = []

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def current_path(self) -> Optional[str]:
        return self._current_path

    def start(self, path: str, working_dir: str | None = None) -> bool:
        """启动脚本；命令不支持或已有任务运行时返回 False。"""
        if self.is_running():
            return False
        plan = build_run_plan(path)
        if plan is None:
            self.run_finished.emit(-1, "failed_to_start")
            return False
        self._current_path = path
        self._cleanup = list(plan.cleanup)
        self.process.setWorkingDirectory(working_dir or plan.cwd)
        self.started.emit(f"> {plan.display}")
        self.process.start(plan.command[0], plan.command[1:])
        return True

    def stop(self) -> None:
        if self.is_running():
            self.process.kill()

    # ---- 内部槽 ----------------------------------------------------------
    def _read_output(self) -> None:
        from ..terminal.terminal import decode_process_bytes

        data = bytes(self.process.readAllStandardOutput())
        text = decode_process_bytes(data)
        if text:
            self.output_emitted.emit(text)

    def _on_finished(self, code: int, status) -> None:
        status_text = (
            "normal"
            if status == QProcess.ExitStatus.NormalExit
            else "crashed"
        )
        cleanup_artifacts(self._cleanup)
        self._cleanup = []
        self.run_finished.emit(code, status_text)
        self._current_path = None

    def _on_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.output_emitted.emit(
                "错误：无法启动解释器/编译器（如 java/javac、gcc/g++、node），"
                "请确认它已安装并在 PATH 中。\n"
            )
            cleanup_artifacts(self._cleanup)
            self._cleanup = []
            self.run_finished.emit(-1, "failed_to_start")
            self._current_path = None
