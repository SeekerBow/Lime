# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""lime 的 LSP（Language Server Protocol）集成。

- :mod:`lime.lsp.protocol`：与 Qt/服务器无关的纯逻辑（消息帧、URI、数据类）
- :mod:`lime.lsp.client`：基于 QProcess 的单个语言服务器连接
- :mod:`lime.lsp.service`：多服务器管理、文档同步防抖、设置联动
- :mod:`lime.lsp.completion`：智能补全弹窗与控制器
- :mod:`lime.lsp.problems_panel`：实时诊断列表面板

当前内置 clangd（C/C++/Objective-C）。clangd 为外部工具，
不随 lime.exe 分发，需自行安装并保证其在 PATH 中（或在设置里指定路径）。
"""
