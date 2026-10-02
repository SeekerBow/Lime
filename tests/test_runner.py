"""runner 模块单元测试（含真实子进程集成）。"""

import os
import shutil
import sys

import pytest

from lime.runner.output_panel import OutputPanel
from lime.runner.runner import (
    IS_WINDOWS,
    CodeRunner,
    RunPlan,
    build_command,
    build_run_plan,
    cleanup_artifacts,
    compiled_shell_line,
    supported_extensions,
)
from tests.conftest import run_event_loop_until

HAS_JAVAC = shutil.which("javac") is not None
HAS_GCC = shutil.which("gcc") is not None
HAS_GPP = shutil.which("g++") is not None


def test_build_python_command():
    command = build_command("script.py")
    assert command == [sys.executable, "script.py"]


def test_build_node_command():
    assert build_command("app.js") == ["node", "app.js"]


def test_build_powershell_command():
    command = build_command("deploy.ps1")
    assert command[0] == "powershell"
    assert "-File" in command


def test_unknown_extension():
    assert build_command("notes.unknown_ext") is None


def test_supported_extensions_contains_py():
    exts = supported_extensions()
    assert ".py" in exts
    assert ".java" in exts
    assert ".c" in exts
    assert ".cpp" in exts
    assert ".cc" in exts and ".cxx" in exts


# ---- 编译型语言：命令计划（纯逻辑）----
def test_compiled_shell_line_java():
    line = compiled_shell_line("/x/App.java", "java", "/tmp/out")
    assert 'javac -encoding UTF-8 -d "/tmp/out" "App.java"' in line
    assert 'java -cp "/tmp/out" "App"' in line
    assert "&&" in line


def test_compiled_shell_line_c_and_cpp():
    line_c = compiled_shell_line("/x/main.c", "c", "/tmp/out")
    assert line_c.startswith('gcc "main.c" -o')
    assert "&&" in line_c
    line_cpp = compiled_shell_line("/x/main.cpp", "c++", "/tmp/out")
    assert line_cpp.startswith('g++ "main.cpp" -o')


def test_compiled_shell_line_unknown_language():
    with pytest.raises(ValueError):
        compiled_shell_line("x.c", "rust", "/tmp/out")


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows bat 计划测试")
def test_windows_java_plan_uses_batch():
    plan = build_run_plan(r"C:\proj\Hello.java")
    assert isinstance(plan, RunPlan)
    assert os.path.isdir(plan.cwd) or plan.cwd == r"C:\proj"
    assert plan.command[0].lower().endswith("cmd.exe")
    assert plan.command[1] == "/c"
    batch = plan.command[2]
    assert batch.endswith(".bat")
    assert os.path.isfile(batch)
    content = open(batch, encoding="mbcs").read()
    assert "javac -encoding UTF-8" in content
    assert "java -cp" in content
    assert "Hello.java" in content
    assert batch in plan.cleanup
    assert any(os.path.isdir(p) for p in plan.cleanup)
    cleanup_artifacts(plan.cleanup)


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows bat 计划测试")
@pytest.mark.parametrize(
    "source,compiler",
    [("main.c", "gcc"), ("main.cpp", "g++"), ("main.cc", "g++")],
)
def test_windows_c_family_plan_batch(source, compiler):
    plan = build_run_plan(os.path.join(r"C:\proj", source))
    batch = plan.command[2]
    content = open(batch, encoding="mbcs").read()
    assert f"{compiler} -static" in content
    assert "main.exe" in content
    assert "if errorlevel 1 exit /b 1" in content
    cleanup_artifacts(plan.cleanup)


# ---- 编译型语言：真实工具链集成 ----
def _run_and_collect(path):
    runner = CodeRunner()
    output: list[str] = []
    result: dict = {}
    runner.output_emitted.connect(output.append)
    runner.run_finished.connect(
        lambda code, status: result.update(code=code, status=status)
    )
    runner.start(str(path))
    run_event_loop_until(runner.run_finished, timeout_ms=60000)
    return runner, "".join(output), result


@pytest.mark.skipif(not HAS_JAVAC, reason="需要 JDK（javac）")
def test_run_java_compile_and_run(qapp, tmp_path):
    source = tmp_path / "HelloJava.java"
    source.write_text(
        "public class HelloJava {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"lime_java_token_55\");\n"
        "    }\n}\n",
        encoding="utf-8",
    )
    runner, output, result = _run_and_collect(source)
    assert result["status"] == "normal"
    assert result["code"] == 0
    assert "lime_java_token_55" in output
    # 临时构建产物已清理
    assert runner._cleanup == []
    leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".class")]
    assert leftovers == []


@pytest.mark.skipif(not HAS_JAVAC, reason="需要 JDK（javac）")
def test_run_java_compile_error_nonzero(qapp, tmp_path):
    source = tmp_path / "Broken.java"
    source.write_text("public class Broken { this is not java }\n", encoding="utf-8")
    _, output, result = _run_and_collect(source)
    assert result["code"] != 0
    assert "error" in output.lower() or "错误" in output


@pytest.mark.skipif(not HAS_GCC, reason="需要 gcc")
def test_run_c_compile_and_run(qapp, tmp_path):
    source = tmp_path / "hello.c"
    source.write_text(
        '#include <stdio.h>\n'
        "int main(void) { printf(\"lime_c_token_55\\n\"); return 0; }\n",
        encoding="utf-8",
    )
    _, output, result = _run_and_collect(source)
    assert result["status"] == "normal"
    assert result["code"] == 0
    assert "lime_c_token_55" in output
    assert not list(tmp_path.glob("*.exe"))


@pytest.mark.skipif(not HAS_GPP, reason="需要 g++")
def test_run_cpp_compile_and_run(qapp, tmp_path):
    source = tmp_path / "hello.cpp"
    source.write_text(
        "#include <iostream>\n"
        "int main() { std::cout << \"lime_cpp_token_55\" << std::endl; "
        "return 0; }\n",
        encoding="utf-8",
    )
    _, output, result = _run_and_collect(source)
    assert result["status"] == "normal"
    assert result["code"] == 0
    assert "lime_cpp_token_55" in output
    assert not list(tmp_path.glob("*.exe"))


@pytest.mark.skipif(not IS_WINDOWS or not HAS_GCC, reason="Windows + gcc")
def test_run_c_with_spaces_in_path(qapp, tmp_path):
    project = tmp_path / "dir with spaces"
    project.mkdir()
    source = project / "spaced.c"
    source.write_text(
        '#include <stdio.h>\nint main(void){printf("spaced_token_55\\n");return 0;}\n',
        encoding="utf-8",
    )
    _, output, result = _run_and_collect(source)
    assert result["code"] == 0, result
    assert "spaced_token_55" in output


def test_run_python_script(qapp, tmp_path):
    script = tmp_path / "hello.py"
    script.write_text(
        "print('lime_runner_token_42')\nimport sys; sys.exit(0)\n", encoding="utf-8"
    )
    runner = CodeRunner()
    output: list[str] = []
    result: dict = {}
    runner.output_emitted.connect(output.append)
    runner.run_finished.connect(lambda code, status: result.update(code=code, status=status))

    assert runner.start(str(script)) is True
    run_event_loop_until(runner.run_finished, timeout_ms=20000)

    assert result.get("status") == "normal"
    assert result.get("code") == 0
    assert "lime_runner_token_42" in "".join(output)
    assert runner.is_running() is False


def test_run_nonzero_exit_code(qapp, tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    runner = CodeRunner()
    result: dict = {}
    runner.run_finished.connect(lambda code, status: result.update(code=code, status=status))
    runner.start(str(script))
    run_event_loop_until(runner.run_finished, timeout_ms=20000)
    assert result["code"] == 3
    assert result["status"] == "normal"


def test_unsupported_file_failed_signal(qapp, tmp_path):
    runner = CodeRunner()
    result: dict = {}
    runner.run_finished.connect(lambda code, status: result.update(code=code, status=status))
    assert runner.start(str(tmp_path / "x.zzz")) is False
    assert result["status"] == "failed_to_start"


def test_output_panel_runs_file(qapp, tmp_path):
    script = tmp_path / "panel.py"
    script.write_text("print('panel_output_token')\n", encoding="utf-8")
    panel = OutputPanel()
    assert panel.run_file(str(script)) is True
    run_event_loop_until(panel.runner.run_finished, timeout_ms=20000)
    assert "panel_output_token" in panel.text()
    assert "退出码 0" in panel.status_label.text()
