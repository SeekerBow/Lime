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
