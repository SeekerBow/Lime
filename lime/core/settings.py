"""设置持久化：对 :class:`QSettings` 的类型安全封装。

默认写入系统持久化后端（Windows 注册表 / macOS plist / Linux ini），
测试时可注入一个使用 ``IniFormat`` 的 QSettings 实例。
"""

from __future__ import annotations

from typing import Any, Iterable

from PyQt6.QtCore import QByteArray, QSettings


class Settings:
    """带默认值与便捷属性的配置访问对象。"""

    # key -> 默认值
    DEFAULTS: dict[str, Any] = {
        # 编辑器
        "editor/font_family": "Consolas",
        "editor/font_size": 11,
        "editor/tab_width": 4,
        "editor/spaces_instead_of_tabs": True,
        "editor/line_numbers": True,
        "editor/word_wrap": False,
        "editor/highlight_style": "default",
        # 主题
        "theme": "default",
        # 文件浏览器
        "filebrowser/last_dir": "",
        # Ollama
        "ollama/host": "http://127.0.0.1:11434",
        "ollama/model": "",
        "ollama/timeout": 60,
        # 终端：空字符串表示自动探测
        "terminal/shell": "",
        # LSP（clangd 实时诊断与智能补全）
        "lsp/enabled": True,
        "lsp/clangd_command": "clangd",
    }

    RECENT_FILES_KEY = "recent/files"
    MAX_RECENT = 10

    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._s = qsettings if qsettings is not None else QSettings(
            "lime", "lime"
        )

    # ---- 通用读写 -------------------------------------------------------
    @property
    def raw(self) -> QSettings:
        """暴露底层 QSettings（用于窗口几何等特殊值）。"""
        return self._s

    def get(self, key: str, default: Any = None) -> Any:
        default = self.DEFAULTS.get(key, default)
        return self._s.value(key, default)

    def set(self, key: str, value: Any) -> None:
        self._s.setValue(key, value)

    def sync(self) -> None:
        self._s.sync()

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """INI 后端可能把布尔读回为字符串，这里统一归一化。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)

    # ---- 编辑器 ---------------------------------------------------------
    @property
    def font_family(self) -> str:
        return str(self.get("editor/font_family"))

    @font_family.setter
    def font_family(self, value: str) -> None:
        self.set("editor/font_family", value)

    @property
    def font_size(self) -> int:
        return int(self.get("editor/font_size"))

    @font_size.setter
    def font_size(self, value: int) -> None:
        self.set("editor/font_size", int(value))

    @property
    def tab_width(self) -> int:
        return int(self.get("editor/tab_width"))

    @tab_width.setter
    def tab_width(self, value: int) -> None:
        self.set("editor/tab_width", int(value))

    @property
    def spaces_instead_of_tabs(self) -> bool:
        return self._to_bool(self.get("editor/spaces_instead_of_tabs"))

    @spaces_instead_of_tabs.setter
    def spaces_instead_of_tabs(self, value: bool) -> None:
        self.set("editor/spaces_instead_of_tabs", bool(value))

    @property
    def line_numbers(self) -> bool:
        return self._to_bool(self.get("editor/line_numbers"))

    @line_numbers.setter
    def line_numbers(self, value: bool) -> None:
        self.set("editor/line_numbers", bool(value))

    @property
    def word_wrap(self) -> bool:
        return self._to_bool(self.get("editor/word_wrap"))

    @word_wrap.setter
    def word_wrap(self, value: bool) -> None:
        self.set("editor/word_wrap", bool(value))

    @property
    def highlight_style(self) -> str:
        return str(self.get("editor/highlight_style"))

    @highlight_style.setter
    def highlight_style(self, value: str) -> None:
        self.set("editor/highlight_style", value)

    # ---- Ollama ---------------------------------------------------------
    @property
    def ollama_host(self) -> str:
        return str(self.get("ollama/host")).rstrip("/")

    @ollama_host.setter
    def ollama_host(self, value: str) -> None:
        self.set("ollama/host", value)

    @property
    def ollama_model(self) -> str:
        return str(self.get("ollama/model"))

    @ollama_model.setter
    def ollama_model(self, value: str) -> None:
        self.set("ollama/model", value)

    @property
    def ollama_timeout(self) -> int:
        return int(self.get("ollama/timeout"))

    @ollama_timeout.setter
    def ollama_timeout(self, value: int) -> None:
        self.set("ollama/timeout", int(value))

    # ---- 终端 -----------------------------------------------------------
    @property
    def terminal_shell(self) -> str:
        return str(self.get("terminal/shell"))

    @terminal_shell.setter
    def terminal_shell(self, value: str) -> None:
        self.set("terminal/shell", value)

    # ---- LSP ------------------------------------------------------------
    @property
    def lsp_enabled(self) -> bool:
        return self._to_bool(self.get("lsp/enabled"))

    @lsp_enabled.setter
    def lsp_enabled(self, value: bool) -> None:
        self.set("lsp/enabled", bool(value))

    @property
    def clangd_command(self) -> str:
        return str(self.get("lsp/clangd_command"))

    @clangd_command.setter
    def clangd_command(self, value: str) -> None:
        self.set("lsp/clangd_command", value)

    # ---- 文件浏览器 ------------------------------------------------------
    @property
    def last_dir(self) -> str:
        return str(self.get("filebrowser/last_dir"))

    @last_dir.setter
    def last_dir(self, value: str) -> None:
        self.set("filebrowser/last_dir", value)

    # ---- 窗口几何 --------------------------------------------------------
    def geometry(self) -> QByteArray | None:
        value = self._s.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def set_geometry(self, value: QByteArray) -> None:
        self._s.setValue("window/geometry", value)

    def window_state(self) -> QByteArray | None:
        value = self._s.value("window/state")
        return value if isinstance(value, QByteArray) else None

    def set_window_state(self, value: QByteArray) -> None:
        self._s.setValue("window/state", value)

    # ---- 最近打开文件 ----------------------------------------------------
    def recent_files(self) -> list[str]:
        value = self._s.value(self.RECENT_FILES_KEY, [])
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return [str(v) for v in value]

    def add_recent_file(self, path: str) -> None:
        files = [p for p in self.recent_files() if p != path]
        files.insert(0, path)
        del files[self.MAX_RECENT:]
        self._s.setValue(self.RECENT_FILES_KEY, files)

    def clear_recent_files(self) -> None:
        self._s.remove(self.RECENT_FILES_KEY)

    # ---- 批量导出/导入（设置对话框用）------------------------------------
    def as_dict(self, keys: Iterable[str] | None = None) -> dict[str, Any]:
        keys = list(keys) if keys is not None else list(self.DEFAULTS)
        return {key: self.get(key) for key in keys}
