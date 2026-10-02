"""terminal 模块：集成在编辑器内的交互式 Shell 终端。"""

from .terminal import TerminalWidget, default_shell, strip_ansi

__all__ = ["TerminalWidget", "default_shell", "strip_ansi"]
