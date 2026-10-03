# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""ai 模块：本地 Ollama 客户端、后台线程与 AI 侧边栏。"""

from .ollama_client import OllamaClient, OllamaError
from .worker import ChatWorker, ModelListWorker
from .ai_sidebar import AISidebar

__all__ = [
    "OllamaClient",
    "OllamaError",
    "ChatWorker",
    "ModelListWorker",
    "AISidebar",
]
