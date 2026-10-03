# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""QApplication 引导。

在构造任何 :class:`~lime.core.settings.Settings` / QSettings 之前先设置
组织名与应用名，保证默认 QSettings 落在正确的命名空间。
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from typing import Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

ORGANIZATION_NAME = "lime"
APPLICATION_NAME = "lime"

SMOKE_MARKER = os.path.join(tempfile.gettempdir(), "lime_smoke_ok.txt")
SMOKE_FAIL_MARKER = os.path.join(tempfile.gettempdir(), "lime_smoke_FAIL.txt")


def resource_path(relative: str) -> str:
    """返回资源文件的绝对路径，兼容源码运行与 PyInstaller 冻结环境。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        # lime/app.py -> 项目根目录
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(str(base), relative)


def _apply_windows_app_id() -> None:
    """显式设置 AppUserModelID，使任务栏显示窗口自身图标而非 python.exe。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "lime.codeeditor"
        )
    except Exception:  # noqa: BLE001 - 仅为外观增强，失败可忽略
        pass


def application_icon() -> QIcon:
    """加载应用图标（优先 ico，回退 png）。"""
    for name in ("assets/lime.ico", "assets/lime.png"):
        path = resource_path(name)
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """创建（或复用）QApplication 并设置全局应用信息。"""
    _apply_windows_app_id()
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    QApplication.setOrganizationName(ORGANIZATION_NAME)
    QApplication.setApplicationName(APPLICATION_NAME)
    QApplication.setApplicationDisplayName("lime")
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    return app


def run_smoke(app: QApplication) -> int:
    """自检模式：验证关键依赖在（打包后的）运行环境中可用后退出。

    windowed 程序没有控制台，结果写入临时目录的标记文件，
    退出码 0 表示通过。
    """
    for stale in (SMOKE_MARKER, SMOKE_FAIL_MARKER):
        try:
            os.remove(stale)
        except OSError:
            pass

    def check() -> None:
        try:
            import requests  # noqa: F401

            from .editor.highlighter import AVAILABLE_STYLES, lexer_for_filename
            from .lsp.protocol import (
                MessageFramer,
                encode_message,
                server_for_path,
                uri_to_path,
                path_to_uri,
            )
            from .runner.runner import build_run_plan

            assert lexer_for_filename("Demo.java") is not None, "Java lexer 缺失"
            assert lexer_for_filename("main.cpp") is not None, "C++ lexer 缺失"
            assert lexer_for_filename("main.c") is not None, "C lexer 缺失"
            assert len(AVAILABLE_STYLES) > 10, "Pygments 样式数据缺失"
            assert build_run_plan("Demo.java") is not None, "Java 运行计划缺失"
            assert build_run_plan("main.c") is not None, "C 运行计划缺失"
            assert server_for_path("main.cpp") is not None, "clangd 注册缺失"
            assert uri_to_path(path_to_uri("main.cpp"))
            frame = MessageFramer()
            assert frame.feed(encode_message({"ok": True})) == [{"ok": True}]

            from .core.settings import Settings
            from .ui.main_window import MainWindow

            assert not app.windowIcon().isNull(), "应用图标缺失"
            window = MainWindow(Settings())
            window.show()
            assert window.tabs.count() >= 1
            assert not window.windowIcon().isNull(), "窗口图标缺失"

            with open(SMOKE_MARKER, "w", encoding="utf-8") as fh:
                fh.write("lime smoke OK\n")
            app.exit(0)
        except Exception:  # noqa: BLE001 - 自检需要捕获一切并落盘
            with open(SMOKE_FAIL_MARKER, "w", encoding="utf-8") as fh:
                fh.write(traceback.format_exc())
            app.exit(1)

    # 事件循环启动后再执行，确保窗口/插件完成初始化
    QTimer.singleShot(600, check)
    return app.exec()


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口，返回应用退出码。"""
    args = list(argv) if argv is not None else sys.argv[1:]
    app = create_application(["lime", *args])

    if "--smoke" in args:
        return run_smoke(app)

    # 延迟导入，避免在无显示环境导入模块时提前创建 QApplication。
    from .core.settings import Settings
    from .ui.app_theme import apply_app_theme
    from .ui.main_window import MainWindow

    settings = Settings()
    # 把编辑器配色方案应用到整个窗口（菜单/面板/对话框）
    apply_app_theme(app, settings.highlight_style)
    window = MainWindow(settings)
    window.show()
    return app.exec()
