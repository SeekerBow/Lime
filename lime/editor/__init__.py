# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""editor 模块：语法高亮、代码编辑器控件、多标签文件管理。"""

from .highlighter import PygmentsHighlighter, lexer_for_filename
from .code_editor import CodeEditor
from .tab_manager import TabManager

__all__ = ["PygmentsHighlighter", "lexer_for_filename", "CodeEditor", "TabManager"]
