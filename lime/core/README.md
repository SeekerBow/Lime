# lime.core — 配置基础设施

基于 `QSettings` 的类型安全配置封装，是所有模块持久化偏好的唯一入口。

## 关键类型

### `Settings`

```python
Settings(qsettings: QSettings | None = None)
```

- 不传参时使用默认后端（Windows 注册表 / macOS plist / Linux ini），
  组织名与应用名均为 `lime`；
- 测试时可注入 `QSettings(path, QSettings.Format.IniFormat)`。

主要属性：字体 `font_family/font_size`、缩进 `tab_width/spaces_instead_of_tabs`、
`line_numbers/word_wrap/highlight_style`、`ollama_host/ollama_model/ollama_timeout`、
`terminal_shell`、`last_dir`、窗口几何 `geometry()/set_geometry()`、
最近文件 `recent_files()/add_recent_file()/clear_recent_files()`。

所有默认值集中在 `Settings.DEFAULTS`，布尔读取对 INI 后端的 `"true"/"false"`
字符串做了归一化。

## 测试

`tests/test_settings.py`：默认值、类型化读写、跨进程 INI 持久化、
host 末尾斜杠、最近文件去重/上限、窗口几何存取。
