# lime.search — 查找替换

纯逻辑、编辑器引擎、工具条 UI 三层分离。

## API

- `compile_pattern(pattern, case_sensitive, whole_word, use_regex) -> re.Pattern`
  纯文本模式自动 `re.escape`，整词模式包裹 `\b`，非法正则抛 `re.error`。
- `find_all(text, ...) -> list[(start, end)]`。
- `FindReplaceEngine(editor)`
  - `set_pattern()`、`matches()`、`count()`；
  - `find(backward=False)`：统一走正则实现，支持循环查找；
  - `replace_one(replacement)`、`replace_all(replacement) -> 数量`，
    全部替换支持 `\1`、`\g<name>` 反向引用。
- `FindReplaceBar(QWidget)`：查找/替换输入、三个选项复选框、
  上一个/下一个/替换/全部替换、实时匹配计数与正则错误提示，
  Esc 关闭；`attach(editor)` 绑定当前标签。

## 快捷键

- `Ctrl+F` 查找，`Ctrl+H` 替换（在主窗口注册）。

## 测试

`tests/test_find_replace.py`：大小写、整词、正则、纯文本转义、
向前/向后/循环、无匹配、单个与全部替换（含反向引用）、
工具条计数与错误提示。
