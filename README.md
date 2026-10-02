# lime

> 一个新手用 AI 写的小玩具级别代码编辑器，不喜勿喷

Python + PyQt6 编写的轻量桌面代码编辑器。语法高亮由 Pygments 提供，
AI 能力对接本地 Ollama（`http://127.0.0.1:11434`，数据不出本机），
配置通过 `QSettings` 持久化。

## 功能

- **多标签编辑**：新建/打开/保存/另存，未保存关闭时三选一确认，脏标记 `•`
- **语法高亮与主题**：Pygments lexer 自动匹配（Python/JavaScript/**Java/C/C++**/Go 等），
  正确支持 C/C++/Java 的 `/* ... */` 多行注释等跨行结构；内置全部 Pygments 样式，
  并额外内置 **One Dark Pro、Tokyo Night、Catppuccin Mocha、GitHub Dark Dimmed**
  四款流行深色主题；切换主题后编辑器背景、选中色、行号栏、当前行高亮同步变化
- **代码编辑**：默认 4 格缩进（空格与物理 Tab 显示宽度一致），回车保持缩进，
  `{` / `:` 后自动增加一级缩进
- **实时代码解析（LSP/clangd）**：打开 C/C++ 文件自动启动 clangd，
  错误/警告以下划波浪线标记，悬停查看完整诊断；底部“问题”面板汇总全部文件，
  **F8 / Shift+F8** 在问题间跳转
- **智能代码补全（LSP）**：边打字边弹出无焦点补全列表（`.`/`->`/`::` 成员触发，
  **Ctrl+空格** 手动触发），↑↓ 选择、Tab/回车确认、Esc 取消；
  支持 textEdit 范围替换
- **文件浏览器**：目录树、双击打开、右键新建/重命名/删除，记忆上次目录
- **查找替换**：区分大小写、整词、正则（支持反向引用替换）、循环查找
- **一键运行（F5）**：
  - 解释型：`.py/.js/.mjs/.bat/.cmd/.ps1/.sh/.rb/.go`
  - 编译型：**`.java`（JDK）、`.c`（gcc）、`.cpp/.cc/.cxx`（g++）**，
    自动编译到临时目录、运行产物、结束后清理
  - 实时输出（自动兼容 GBK 编译器诊断）、退出码、可停止
- **集成终端**：Windows `cmd.exe` / POSIX `bash`，控制键透传，ANSI 自动清理
- **AI 侧边栏**：模型列表刷新、流式回答、一键附带当前文件/选中文本、可停止、错误友好提示
- **设置持久化**：字体/缩进/行号/换行/高亮样式、Ollama 地址与模型、终端 Shell、
  最近文件、窗口几何，全部写入 QSettings

## 快速开始

```bash
# 1. 安装依赖（Python 3.10+）
python -m pip install -r requirements.txt

# 2. 启动（两种方式等价）
python main.py
python -m lime

# 3.（可选）启动本地 Ollama 并拉取模型
ollama serve
ollama pull qwen2.5-coder:7b
# 打开 AI 侧边栏后点“刷新”选择模型
```

编译运行 Java/C/C++ 需要本机工具链在 PATH 中（编辑器本身不依赖它们）：

- Java：安装 JDK（提供 `javac`、`java`）
- C/C++：Windows 推荐 [MinGW-w64](https://www.mingw-w64.org/)（提供 `gcc`、`g++`）

实时诊断与智能补全为可选能力，需要 **clangd**（C/C++ 语言服务器），
它**不随 lime.exe 分发**：

- Windows 可安装 [LLVM](https://github.com/llvm/llvm-project/releases)
  （其中含 clangd），或使用 CP Editor 自带的 clangd；
- 确保 `clangd`（或 `clangd.exe`）在 PATH 中，也可在“设置 → clangd 路径”
  填写完整路径；未找到时打开 C/C++ 文件会在状态栏给出友好提示，其余功能不受影响；
- 可在设置中整体关闭 LSP。

## 打包为单文件 exe（免安装、无外部依赖）

```bash
python -m pip install pyinstaller
# 用固化好的 lime.spec 构建（已含应用图标、Pygments 资源、assets 数据）
python -m PyInstaller --noconfirm --clean lime.spec
# 产物：dist/lime.exe（约 66 MB）—— 双击即可运行，可拷贝到任意 Windows 机器
```

- 应用图标 `assets/lime.ico`（青柠切片 logo，16–256 多尺寸）同时嵌入 exe
  并在运行时用于窗口/任务栏（已设置 Windows AppUserModelID）；
- 通过 `--collect-all pygments` 收全 Pygments 的 lexer/样式数据与包元数据，
  确保冻结环境下语法高亮与所有内置样式可用。

发布前可用自检模式快速验证打包产物（PyQt6/Pygments/requests 均正常）：

```bash
dist\lime.exe --smoke
echo %ERRORLEVEL%   # 0 表示自检通过
```

## 运行测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

GUI 测试自动使用 Qt 的 `offscreen` 平台插件，无需显示器；
其中包含真实子进程（Python 脚本、Windows cmd）集成用例。

## 常用快捷键

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S | 新建 / 打开 / 保存 / 另存 |
| Ctrl+F / Ctrl+H | 查找 / 替换（Esc 关闭） |
| F5 | 运行当前文件 |
| Ctrl+空格 | 手动触发智能补全 |
| F8 / Shift+F8 | 下一个 / 上一个诊断问题 |
| Tab | 插入空格并对齐 Tab stop（可配置宽度） |
| Ctrl+C（终端内） | 中断当前命令 |
| Ctrl+Enter（AI 输入框） | 发送问题 |

## 项目结构

```
lime/
├── main.py                     # 启动入口
├── requirements.txt / -dev.txt
├── docs/requirements.md        # 需求文档
├── lime/
│   ├── app.py                  # QApplication 引导
│   ├── core/                   # Settings（QSettings）         见模块 README
│   ├── editor/                 # 高亮 / 主题 / CodeEditor / TabManager
│   ├── filebrowser/            # 文件浏览器
│   ├── search/                 # 查找替换
│   ├── runner/                 # 一键运行 + 输出面板
│   ├── terminal/               # 集成终端
│   ├── lsp/                    # LSP 协议/clangd 客户端/补全/问题面板
│   ├── ai/                     # Ollama 客户端 / 线程 / 侧边栏
│   └── ui/                     # 主窗口 / 设置对话框
└── tests/                      # 每模块一组 pytest + conftest
```

每个模块目录下都有独立 `README.md` 说明公开 API 与测试范围；
需求与验收标准见 [docs/requirements.md](docs/requirements.md)。

## 架构约定

- 可脱离 GUI 测试的核心逻辑（配置、命令构造、正则、ANSI 清理、HTTP 客户端、LSP 协议）
  都是普通类/纯函数；
- 网络与长任务通过 `QThread`/`QProcess` 异步执行，不阻塞 UI；
- 模块间通过 Qt 信号解耦（如 `FileBrowser.file_open_requested` →
  `TabManager.open_file`）。

## 许可证

[GPL-3.0](LICENSE)
