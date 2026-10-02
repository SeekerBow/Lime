# lime.editor — 编辑器内核

语法高亮、代码编辑器控件与多标签文件管理。

## 组成

| 文件 | 职责 |
| --- | --- |
| `themes.py` | 自定义 Pygments 样式（One Dark Pro 等）+ 颜色工具 |
| `highlighter.py` | Pygments → Qt 桥接 |
| `code_editor.py` | 行号栏、当前行高亮、缩进、诊断标记 |
| `tab_manager.py` | 多标签：新建/打开/保存/另存/关闭 |

## 公开 API

- `themes.py`：`OneDarkProStyle` / `TokyoNightStyle` /
  `CatppuccinMochaStyle` / `GitHubDarkDimmedStyle` 四款自定义
  `pygments.style.Style`；`CUSTOM_STYLES`、`AVAILABLE_STYLE_NAMES`、
  `get_style(name)`（先查自定义再查内置）；颜色工具 `hex_to_rgb`、
  `rgb_to_hex`、`mix_color(first, second, t)`、`is_dark(color)`。
- `lexer_for_filename(path) -> Lexer | None`：按扩展名选择 Pygments lexer。
  内置支持所有 Pygments 自带语言，常用包括 Python、JavaScript、
  **Java（`.java`）、C（`.c`/`.h`）、C++（`.cpp`/`.cc`/`.cxx`/`.hpp`/`.hxx`）**、
  Go、Rust、Shell、Markdown、JSON 等；无法识别时不高亮。
- `PygmentsHighlighter(document, lexer=None, style_name="default")`
  - `set_lexer()` / `set_style()` / `background_color()`；
  - token → `QTextCharFormat` 的解析结果带缓存；
  - **始终对整份文档做一次词法分析**，把含换行的 token（C/C++/Java 的
    `/* ... */` 多行注释、Python 三引号字符串、行延续宏等）拆分回各文本块，
    以块状态跟踪跨行结构：编辑开闭符时后续行会自动重新着色；
    文件末尾未闭合的注释也按注释色显示；
  - 整文档结果按 `QTextDocument.revision()` 缓存，每次编辑只重建一次。
- `CodeEditor(QPlainTextEdit)`
  - `apply_settings(settings)`；
  - `set_tab_width / set_spaces_instead_of_tabs / set_word_wrap / set_line_numbers_visible`；
  - Tab 默认 **4 格**：按键插入对齐到 4 的空格，物理制表符的显示宽度
    （`tabStopDistance`）也同步为 4 个字符；
  - Tab 插入对齐空格；回车保留缩进，行尾 `{`（C/C++/Java）或 `:`（Python）
    自动增加一级缩进；
  - 主题配色：`apply_color_scheme(background, foreground)` 同步设置
    QPalette、选中色（自动与底色混合）、行号栏与当前行颜色；
  - LSP 诊断：`set_diagnostics(list)` / `diagnostics()` /
    `diagnostic_at(line, column)` / `goto_next_diagnostic(forward=True)`
    （返回诊断对象或 `None`，跳转并居中）；错误/警告/信息/提示以不同颜色
    画波浪下划线，悬停（ToolTip 事件）显示 `来源: 消息`；
  - `completion_controller` 槽位由主窗口挂接智能补全，Ctrl+空格手动触发；
  - `cursor_position() -> (行, 列)`。
- `TabManager(QTabWidget)`
  - `new_document / open_file / open_paths / save_current / save_current_as`；
  - `close_tab / confirm_close_all`（未保存弹 保存/不保存/取消）；
  - 信号 `current_file_changed`、`modification_changed`、`file_tracked`、
    `editor_created(object)`、`file_opened(str)`、`file_saved(path, old_path)`、
    `file_closed(str)`（供 LSP 等外部模块挂接生命周期）；`editor_for_path(path)`
    按归一化路径反查编辑器；
  - 同一文件重复打开只会切换到已有标签；修改中标签标题前缀 `•`。

## 说明

每次文档修订会对整份文档重新词法分析一次（结果在同一次重高亮内缓存）。
对超大文件可能有可感知的延迟，常规源码文件（数千行以内）无影响。

## 测试

`tests/test_highlighter.py`、`tests/test_code_editor.py`、
`tests/test_tab_manager.py` 覆盖 lexer 选择、自定义主题注册与配色、
格式映射、
**C/C++/Java 跨行注释着色与块状态、未闭合注释、跨行字符串、
编辑后状态联动**、行号宽度、Tab 制表位距离与 4 格缩进、花括号回车缩进、
脏标记、保存、关闭确认三分支与设置刷新。诊断波浪线/F8 跳转逻辑由
`tests/test_lsp_integration.py` 覆盖。
