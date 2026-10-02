"""editor 模块：语法高亮、代码编辑器控件、多标签文件管理。"""

from .highlighter import PygmentsHighlighter, lexer_for_filename
from .code_editor import CodeEditor
from .tab_manager import TabManager

__all__ = ["PygmentsHighlighter", "lexer_for_filename", "CodeEditor", "TabManager"]
