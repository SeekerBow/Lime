# lime 桌面代码编辑器 — 需求文档

- 版本：1.0
- 日期：2026-10-01
- 技术栈：Python 3.10+ / PyQt6 / Pygments / requests / QSettings / Ollama

## 1. 项目概述

lime 是一个使用 Python + PyQt6 开发的轻量级桌面代码编辑器，面向日常脚本编写与快速实验场景。
它提供多标签编辑、语法高亮、文件浏览、查找替换、一键运行、集成终端以及基于本地 Ollama 的 AI
辅助侧边栏，并通过 `QSettings` 持久化所有用户配置。

AI 能力默认对接本地 Ollama 服务（`http://127.0.0.1:11434`），代码补全/问答数据不出本机。

## 2. 目标用户与典型场景

- 编写并即时运行 Python / Node / Shell 等单文件脚本；
- 在一个工程目录内快速浏览、打开、重命名、删除文件；
- 在大文件中按正则/整词/区分大小写查找替换；
- 不离开编辑器在集成终端中执行命令；
- 选中代码后让本地大模型解释或改写代码。

## 3. 功能需求

### FR-1 多标签编辑

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-1.1 | 新建/打开多个文档，每个文档一个标签 | 标签数随打开文件增加，标签显示文件名 |
| FR-1.2 | 文件修改后标签标题显示 `•` 脏标记 | 修改文本后标题前缀出现圆点，保存后消失 |
| FR-1.3 | 保存（Ctrl+S）/ 另存为（Ctrl+Shift+S） | 保存后磁盘文件内容与编辑器一致，脏标记清除 |
| FR-1.4 | 关闭未保存标签时弹出保存确认 | 选择“保存”写入文件、“不保存”直接关闭、“取消”保留标签 |
| FR-1.5 | 重复打开同一文件时切换到已有标签 | 同一磁盘文件不会出现两个标签 |
| FR-1.6 | 关闭窗口时批量确认所有未保存文档 | 任一标签选“取消”则窗口不关闭 |

### FR-2 语法高亮（Pygments）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-2.1 | 按文件扩展名自动选择 Pygments Lexer | `.py` → Python，`.js` → JavaScript，`.java` → Java，`.c/.h` → C，`.cpp/.cc/.cxx/.hpp` → C++，无匹配则不高亮 |
| FR-2.2 | 关键字、字符串、注释、数字等着色不同 | 编辑器内 token 应用了不同的 QTextCharFormat |
| FR-2.3 | 行号栏与当前行高亮 | 行号随行数自适应宽度，当前行背景高亮 |
| FR-2.4 | 可配置等宽字体、字号、Tab 宽度、空格替代 Tab | 设置修改后新打开编辑器即时生效 |

说明：高亮以“单行”为粒度驱动 Pygments，跨行字符串等复杂状态不作为 1.0 目标。

### FR-3 文件浏览器

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-3.1 | 选择并展开一个根目录 | 树中显示该目录内容，记住上次目录 |
| FR-3.2 | 双击文件在编辑器中打开 | 发出打开请求并由主窗口新建标签 |
| FR-3.3 | 右键新建文件/文件夹、重命名、删除 | 操作后磁盘与树同步变化 |

### FR-4 查找替换（Ctrl+F / Ctrl+H）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-4.1 | 查找下一个/上一个并选中匹配 | 光标移动到匹配处并选中 |
| FR-4.2 | 支持区分大小写、整词匹配、正则表达式 | 三种开关组合返回正确匹配集合 |
| FR-4.3 | 替换当前匹配 / 全部替换 | 全部替换返回替换数量且文本正确更新 |
| FR-4.4 | 无匹配时状态栏提示且不崩溃 | 返回 0 个匹配 |

### FR-5 一键运行（F5）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-5.1 | 按扩展名生成运行命令 | `.py` → 当前解释器运行脚本；`.js` → node；`.ps1` → powershell；不支持的扩展名给出提示 |
| FR-5.2 | 编译型语言支持 | `.java` 调 `javac` 编译、`java` 运行（要求公共类名与文件名一致）；`.c` 调 gcc、`.cpp/.cc/.cxx` 调 g++ 编译后运行产物 |
| FR-5.3 | 编译产物隔离与清理 | class/可执行文件写入系统临时目录，运行结束自动删除，源码目录无残留 |
| FR-5.4 | 编译失败可见 | 编译错误诊断显示在输出面板，进程退出码非零 |
| FR-5.5 | 在输出面板实时显示 stdout/stderr | 程序输出逐块追加显示；GBK 诊断（中文 Windows javac）不乱码 |
| FR-5.6 | 显示退出码，可中途停止 | 结束显示退出码；停止按钮终止子进程 |
| FR-5.7 | 免安装分发 | 可通过 PyInstaller 打包为单文件 windowed exe，在无 Python 环境的 Windows 机器直接运行 |

### FR-6 集成终端

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-6.1 | 启动本机交互式 Shell | Windows 为 `cmd.exe`，POSIX 为 `$SHELL`/`bash`，可在设置中覆盖 |
| FR-6.2 | 键盘输入发送到 Shell，输出回显 | 输入 `echo hi` 回车后界面出现 hi |
| FR-6.3 | 支持 Backspace、Ctrl+C、方向键 | 发送对应控制字符 |
| FR-6.4 | ANSI 转义序列被清理 | 输出中不残留 ESC 颜色码 |

### FR-7 AI 侧边栏（本地 Ollama）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-7.1 | 通过 `requests` 访问 `http://127.0.0.1:11434` | 使用 `/api/tags` 拉取模型、`/api/chat` 对话 |
| FR-7.2 | 流式显示回答 | 模型分片返回时界面逐块追加 |
| FR-7.3 | 可选择模型、刷新模型列表 | 下拉框显示 Ollama 已安装模型 |
| FR-7.4 | 一键附带当前编辑器文件/选中文本作为上下文 | 消息载荷中包含代码上下文 |
| FR-7.5 | Ollama 不可达时友好报错，不崩溃 | 网络错误转化为界面错误提示 |
| FR-7.6 | 网络请求在后台线程执行，界面不卡死 | 使用 QThread，提供停止按钮 |

### FR-8 设置持久化（QSettings）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-8.1 | 编辑器字体/字号/Tab/空格/行号/自动换行持久化 | 重启后设置值恢复 |
| FR-8.2 | Ollama host/model、终端 Shell 持久化 | 重启后值恢复 |
| FR-8.3 | 最近打开目录持久化 | 重启后文件浏览器定位到上次目录 |
| FR-8.4 | 窗口几何布局持久化 | 重启后窗口大小/位置恢复 |
| FR-8.5 | 设置对话框可修改上述配置 | 修改保存后即时生效 |

### FR-9 颜色主题

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-9.1 | 提供多款颜色主题 | 除 Pygments 内置样式外，内置 One Dark Pro、Tokyo Night、Catppuccin Mocha、GitHub Dark Dimmed 四款自定义样式 |
| FR-9.2 | 切换主题后编辑器整体配色联动 | 背景/前景/选中色/行号栏/当前行高亮随主题（深/浅）更新，已有标签即时生效 |
| FR-9.3 | 主题选择持久化 | 重启后恢复上次选择的样式 |

### FR-10 实时代码解析与智能补全（LSP）

| 编号 | 需求 | 验收标准 |
| --- | --- | --- |
| FR-10.1 | 通过 LSP 接入 C/C++ 语言服务器 clangd | 打开 `.c/.cpp/...` 文件自动启动 clangd 并完成 initialize 握手（Content-Length 分帧 JSON-RPC） |
| FR-10.2 | 实时诊断 | publishDiagnostics 以错误/警告/信息/提示四级波浪下划线显示，悬停展示来源与消息；编辑后约 300 ms 防抖增量同步 |
| FR-10.3 | 问题面板与导航 | 底部面板按严重级别列出全部打开文件的诊断并显示错误/警告计数，双击跳转；F8/Shift+F8 在当前文件问题间循环跳转 |
| FR-10.4 | 智能补全 | 标识符输入及 `.`/`->`/`::` 触发字符自动请求，Ctrl+空格手动触发；无焦点弹窗支持 ↑↓/Tab/回车/Esc；优先应用 textEdit 范围替换 |
| FR-10.5 | clangd 为可选外部工具，不随 exe 分发 | 未安装/路径错误时状态栏友好提示，编辑器其余功能正常；可在设置中关闭 LSP 或配置 clangd 路径 |
| FR-10.6 | 文档生命周期正确 | 打开 didOpen、修改 didChange、保存 didSave、关闭 didClose；另存为按旧路径 didClose、新路径 didOpen |

## 4. 非功能需求

- NFR-1：跨平台（Windows 优先，POSIX Shell 逻辑保留）；
- NFR-2：所有网络/长任务不得阻塞 UI 线程；
- NFR-3：每个模块具备独立单元测试，`pytest` 全绿；GUI 测试在 `offscreen` 平台插件下运行；
- NFR-4：模块间通过信号/明确接口通信，核心逻辑（命令构造、正则编译、ANSI 清理、HTTP 客户端）
  保持为可脱离 GUI 测试的纯函数/普通类；
- NFR-5：第三方依赖仅 PyQt6、Pygments、requests。

## 5. 项目结构

```
lime/
├── main.py                     # 启动入口
├── requirements.txt            # 运行依赖
├── requirements-dev.txt        # 测试依赖
├── docs/
│   └── requirements.md         # 本文件
├── lime/
│   ├── __init__.py
│   ├── __main__.py             # python -m lime
│   ├── app.py                  # QApplication 引导
│   ├── core/                   # 配置（QSettings）
│   ├── editor/                 # 高亮、代码编辑器、多标签管理
│   ├── filebrowser/            # 文件浏览器
│   ├── search/                 # 查找替换
│   ├── runner/                 # 一键运行 + 输出面板
│   ├── terminal/               # 集成终端
│   ├── lsp/                    # LSP 协议、clangd 客户端、补全、问题面板
│   ├── ai/                     # Ollama 客户端、后台线程、AI 侧边栏
│   └── ui/                     # 主窗口、设置对话框
└── tests/                      # 每个模块一组单元测试 + conftest.py
```

每个模块目录附带自己的 `README.md` 说明职责、公开 API 与测试方式。

## 6. 模块职责

| 模块 | 核心类型 | 职责 |
| --- | --- | --- |
| core | `Settings` | QSettings 类型安全封装、默认值、最近目录 |
| editor | `PygmentsHighlighter` / `CodeEditor` / `TabManager` | 高亮、行号、标签与文件读写 |
| filebrowser | `FileBrowser` | 目录树、文件 CRUD、打开请求信号 |
| search | `FindReplaceBar` / `FindReplaceEngine` | 查找替换 UI 与纯逻辑 |
| runner | `CodeRunner` / `OutputPanel` / `build_command` | 子进程运行与输出 |
| terminal | `TerminalWidget` | 交互式 Shell 终端 |
| lsp | `MessageFramer` / `LspClient` / `LspService` / `CompletionController` / `ProblemsPanel` | JSON-RPC 纯逻辑、clangd 进程管理、文档同步防抖、补全弹窗、诊断面板 |
| ai | `OllamaClient` / `OllamaWorker` / `AISidebar` | HTTP 客户端、后台流式线程、聊天界面 |
| ui | `MainWindow` / `SettingsDialog` | 组装全部模块、菜单/快捷键/状态栏 |

## 7. 测试策略

- 纯逻辑：`pytest` 直接断言（命令构造、正则、ANSI、Ollama 客户端用 mock session）；
- GUI：`QT_QPA_PLATFORM=offscreen` 下构造控件，使用临时目录与 IniFormat QSettings；
- 子进程：运行临时脚本并以事件循环等待 `finished` 信号，设超时兜底；
- 每个模块至少覆盖：正常路径、边界/失败路径各一条。

## 8. 里程碑（本次一次性交付）

1. 骨架与需求文档；2. core；3. editor；4. filebrowser；5. search；
6. runner；7. terminal；8. ai；9. ui；10. README 与全量测试通过。
