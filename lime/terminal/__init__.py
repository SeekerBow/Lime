# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""terminal 模块：集成在编辑器内的交互式 Shell 终端。"""

from .terminal import TerminalWidget, default_shell, strip_ansi

__all__ = ["TerminalWidget", "default_shell", "strip_ansi"]
