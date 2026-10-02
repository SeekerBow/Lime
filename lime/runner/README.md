# lime.runner — 一键运行

按文件扩展名构造命令并用 `QProcess` 异步执行，stdout/stderr 合并实时输出。

## 支持的文件类型

### 解释型（直接运行）

| 扩展名 | 命令 |
| --- | --- |
| `.py` | 当前 Python 解释器（`sys.executable`） |
| `.js` / `.mjs` | `node` |
| `.bat` / `.cmd` | `cmd /c`（使用 `%COMSPEC%`） |
| `.ps1` | `powershell -ExecutionPolicy Bypass -File` |
| `.sh` | `bash` |
| `.rb` | `ruby` |
| `.go` | `go run` |

### 编译型（编译到临时目录后运行产物）

| 扩展名 | 语言 | 工具链 | 行为 |
| --- | --- | --- | --- |
| `.java` | Java | JDK（`javac`/`java`） | `javac -encoding UTF-8 -d <tmp>` 后 `java -cp <tmp> 类名` |
| `.c` | C | `gcc` | 编译为临时可执行文件后运行（Windows 加 `-static`） |
| `.cpp` / `.cc` / `.cxx` | C++ | `g++` | 同上 |

- 编译产物（`.class` / 可执行文件）写入系统临时目录 `lime_build_*`，
  运行结束自动删除，不污染源码目录；
- 编译失败时立即以非零退出码终止并显示编译器诊断；
- POSIX 通过 `sh -c "编译 && 运行"` 执行；Windows 生成临时 `.bat`
  （`mbcs` 编码、路径加引号）执行，规避 `cmd /c` 复合命令的嵌套引号问题；
- 工具链（JDK / MinGW-w64）需自行安装并加入 PATH，缺失时输出明确提示。

## API

- `build_command(path) -> list[str] | None`：扩展名 → 命令行（便捷封装）。
- `build_run_plan(path) -> RunPlan | None`：完整计划
  （命令、工作目录、展示文本、待清理临时路径）。
- `compiled_shell_line(path, language, output_dir)`：POSIX 复合命令（纯函数）。
- `cleanup_artifacts(paths)`：清理临时构建产物。
- `CodeRunner(QObject)`
  - `start(path, working_dir=None) -> bool`、`stop()`、`is_running()`；
  - 信号 `started(str)`、`output_emitted(str)`、
    `run_finished(exit_code, status)`，status 为
    `normal / crashed / failed_to_start`；
  - 合并输出通道，解码优先 UTF-8、回退 GBK/CP936（中文 Windows 的
    javac 诊断），显示前经 ANSI 清理。
- `OutputPanel(QWidget)`：输出区 + 运行/停止/清空按钮 + 状态标签，
  `run_file(path)` 一键驱动 runner。

## 测试

`tests/test_runner.py`：各扩展名命令构造、编译计划结构
（POSIX shell 行、Windows bat 内容）、真实运行临时 Python 脚本、
**本机存在 javac/gcc/g++ 时真实编译运行 Java/C/C++**（含编译失败、
含空格路径、临时产物清理）、启动失败信号、OutputPanel 端到端显示。
工具链缺失时对应用例自动跳过。
