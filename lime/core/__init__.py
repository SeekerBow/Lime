# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""core 模块：跨模块共享的基础设施（当前为配置持久化）。"""

from .settings import Settings

__all__ = ["Settings"]
