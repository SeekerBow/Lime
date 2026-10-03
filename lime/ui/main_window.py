# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""主窗口：组装编辑器、文件浏览器、查找条、输出/终端面板与 AI 侧边栏。"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..ai.ai_sidebar import AISidebar
from ..core.settings import Settings
from ..cph.test_panel import CphPanel
from ..editor.tab_manager import TabManager
from ..filebrowser.file_browser import FileBrowser
from ..lsp.completion import CompletionController
from ..lsp.problems_panel import ProblemsPanel
from ..lsp.service import LspService
from ..runner.output_panel import OutputPanel
from ..runner.runner import supported_extensions
from ..search.find_replace import FindReplaceBar
from ..terminal.terminal import TerminalWidget
from .app_theme import apply_app_theme
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._bound_editors: set[int] = set()

        self.setWindowTitle("lime")
        self.resize(1280, 820)

        # ---- 核心控件 ----
        self.tabs = TabManager(settings, self)
        self.file_browser = FileBrowser(settings, self)
        self.find_bar = FindReplaceBar(self)
        self.output_panel = OutputPanel(self)
        self.terminal = TerminalWidget(settings, self)
        self.cph_panel = CphPanel(settings, self)
        self.ai_sidebar = AISidebar(settings, parent=self)
        self.lsp = LspService(settings, parent=self)
        self.problems_panel = ProblemsPanel(self)

        # ---- 布局 ----
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.addWidget(self.find_bar)
        center_layout.addWidget(self.tabs, 1)

        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.addTab(self.output_panel, "运行输出")
        self.bottom_tabs.addTab(self.cph_panel, "样例测试")
        self.bottom_tabs.addTab(self.problems_panel, "问题")
        self.bottom_tabs.addTab(self.terminal, "终端")

        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.addWidget(self.file_browser)
        self.top_splitter.addWidget(center)
        self.top_splitter.addWidget(self.ai_sidebar)
        self.top_splitter.setStretchFactor(1, 1)
        self.top_splitter.setSizes([240, 720, 320])

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_tabs)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([620, 200])
        self.setCentralWidget(self.main_splitter)

        # ---- 状态栏 ----
        self.cursor_label = QLabel("行 1, 列 1")
        self.lsp_label = QLabel("LSP：待命中（打开 C/C++ 文件后启动 clangd）")
        self.statusBar().addPermanentWidget(self.lsp_label)
        self.statusBar().addPermanentWidget(self.cursor_label)
        self._lsp_server_messages: dict[str, str] = {}

        self._build_menus()
        self._connect_signals()
        self._restore_state()

        # 启动时打开一个空白文档
        self.tabs.new_document()
        if self.settings.last_dir and os.path.isdir(self.settings.last_dir):
            self.file_browser.set_root(self.settings.last_dir)

    # ---- 菜单/动作 -------------------------------------------------------
    def _build_menus(self) -> None:
        bar = self.menuBar()

        # 文件
        file_menu = bar.addMenu("文件(&F)")
        self.act_new = QAction("新建", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_open = QAction("打开…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_save = QAction("保存", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save_as = QAction("另存为…", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_close_tab = QAction("关闭标签", self)
        self.act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
        self.recent_menu = QMenu("最近打开", self)
        self.recent_menu.aboutToShow.connect(self._populate_recent)
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.close)
        for act in (
            self.act_new,
            self.act_open,
            self.act_save,
            self.act_save_as,
            self.act_close_tab,
        ):
            file_menu.addAction(act)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        # 编辑
        edit_menu = bar.addMenu("编辑(&E)")
        act_undo = QAction("撤销", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        act_redo = QAction("重做", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_find = QAction("查找…", self)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        self.act_replace = QAction("替换…", self)
        self.act_replace.setShortcut("Ctrl+H")
        act_undo.triggered.connect(lambda: self.tabs.current_editor() and self.tabs.current_editor().undo())
        act_redo.triggered.connect(lambda: self.tabs.current_editor() and self.tabs.current_editor().redo())
        self.act_find.triggered.connect(self.find_bar.show_find)
        self.act_replace.triggered.connect(self.find_bar.show_replace)
        edit_menu.addActions([act_undo, act_redo])
        edit_menu.addSeparator()
        edit_menu.addActions([self.act_find, self.act_replace])
        edit_menu.addSeparator()
        self.act_next_problem = QAction("下一个问题", self)
        self.act_next_problem.setShortcut("F8")
        self.act_prev_problem = QAction("上一个问题", self)
        self.act_prev_problem.setShortcut("Shift+F8")
        self.act_next_problem.triggered.connect(lambda: self._goto_problem_in_current(forward=True))
        self.act_prev_problem.triggered.connect(lambda: self._goto_problem_in_current(forward=False))
        edit_menu.addActions([self.act_next_problem, self.act_prev_problem])

        # 运行
        run_menu = bar.addMenu("运行(&R)")
        self.act_run = QAction("运行当前文件", self)
        self.act_run.setShortcut("F5")
        self.act_stop = QAction("停止运行", self)
        self.act_run_samples = QAction("运行样例测试", self)
        self.act_run_samples.setShortcut("F6")
        self.act_run.triggered.connect(self.run_current)
        self.act_stop.triggered.connect(self.output_panel.runner.stop)
        self.act_run_samples.triggered.connect(self.run_samples)
        run_menu.addActions(
            [self.act_run, self.act_run_samples, self.act_stop]
        )

        # 终端
        term_menu = bar.addMenu("终端(&T)")
        act_term_restart = QAction("重启终端", self)
        act_term_clear = QAction("清空终端", self)
        act_term_restart.triggered.connect(self._restart_terminal)
        act_term_clear.triggered.connect(self.terminal.clear_terminal)
        term_menu.addActions([act_term_restart, act_term_clear])

        # 视图
        view_menu = bar.addMenu("视图(&V)")
        self.act_toggle_files = QAction("文件浏览器", self, checkable=True)
        self.act_toggle_files.setChecked(True)
        self.act_toggle_ai = QAction("AI 侧边栏", self, checkable=True)
        self.act_toggle_ai.setChecked(True)
        self.act_toggle_bottom = QAction("输出/终端面板", self, checkable=True)
        self.act_toggle_bottom.setChecked(True)
        self.act_toggle_files.toggled.connect(self.file_browser.setVisible)
        self.act_toggle_ai.toggled.connect(self.ai_sidebar.setVisible)
        self.act_toggle_bottom.toggled.connect(self.bottom_tabs.setVisible)
        view_menu.addActions(
            [self.act_toggle_files, self.act_toggle_ai, self.act_toggle_bottom]
        )
        view_menu.addSeparator()
        self.act_zoom_in = QAction("放大字体", self)
        self.act_zoom_in.setShortcuts(
            [QKeySequence("Ctrl+="), QKeySequence("Ctrl++"),
             QKeySequence("Ctrl+Up")]
        )
        self.act_zoom_out = QAction("缩小字体", self)
        self.act_zoom_out.setShortcuts(
            [QKeySequence("Ctrl+-"), QKeySequence("Ctrl+Down")]
        )
        self.act_zoom_reset = QAction("还原字体大小", self)
        self.act_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_in.triggered.connect(lambda: self._zoom_font(+1))
        self.act_zoom_out.triggered.connect(lambda: self._zoom_font(-1))
        self.act_zoom_reset.triggered.connect(self._reset_font_size)
        view_menu.addActions(
            [self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset]
        )

        # 设置
        settings_menu = bar.addMenu("设置(&S)")
        act_settings = QAction("偏好设置…", self)
        act_settings.triggered.connect(self.open_settings)
        settings_menu.addAction(act_settings)

        # 帮助
        help_menu = bar.addMenu("帮助(&H)")
        act_about = QAction("关于 lime", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _connect_signals(self) -> None:
        self.act_new.triggered.connect(self.tabs.new_document)
        self.act_open.triggered.connect(self.open_files_dialog)
        self.act_save.triggered.connect(self.tabs.save_current)
        self.act_save_as.triggered.connect(self.tabs.save_current_as)
        self.act_close_tab.triggered.connect(self.tabs.close_current)

        self.file_browser.file_open_requested.connect(self.tabs.open_file)
        self.output_panel.run_requested.connect(self.run_current)
        self.find_bar.message.connect(self.statusBar().showMessage)

        self.tabs.file_tracked.connect(self._on_file_tracked)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.tabs.modification_changed.connect(self.act_save.setEnabled)
        self.act_save.setEnabled(False)

        # LSP：编辑器创建 / 文件开关保存 / 诊断
        self.tabs.editor_created.connect(self._on_editor_created)
        self.tabs.file_opened.connect(self._on_lsp_file_opened)
        self.tabs.file_saved.connect(self._on_lsp_file_saved)
        # 未命名文档“另存为”后标签索引不变，需要手动让样例面板重新绑定
        self.tabs.file_saved.connect(lambda path, _old: self.cph_panel.bind(path))
        self.tabs.file_closed.connect(self.lsp.on_closed)
        self.lsp.diagnosticsReceived.connect(self._on_lsp_diagnostics)
        self.lsp.serverStatus.connect(self._on_lsp_server_status)
        self.problems_panel.open_requested.connect(self._goto_diagnostic_location)

        self.ai_sidebar.status_message.connect(self.statusBar().showMessage)
        self.bottom_tabs.currentChanged.connect(self._on_bottom_tab_changed)

        # CPH 样例评测：评测前请求保存当前文件
        self.cph_panel.request_save_current.connect(self._save_current_quietly)

    # ---- 文件操作 --------------------------------------------------------
    def open_files_dialog(self) -> None:
        start = self.settings.last_dir or os.path.expanduser("~")
        filter_text = (
            "所有支持的文件 ("
            + " ".join(f"*{ext}" for ext in supported_extensions())
            + ");;所有文件 (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "打开文件", start, filter_text)
        self.tabs.open_paths(paths)

    def run_current(self) -> None:
        path = self.tabs.current_path()
        if path is None:
            # 未命名文档：先保存再运行
            if not self.tabs.save_current():
                return
            path = self.tabs.current_path()
        if not path:
            return
        self.bottom_tabs.setCurrentWidget(self.output_panel)
        self.bottom_tabs.setVisible(True)
        self.act_toggle_bottom.setChecked(True)
        if not self.output_panel.run_file(path):
            self.statusBar().showMessage("该文件类型不支持一键运行", 5000)

    def run_samples(self) -> None:
        path = self.tabs.current_path()
        if path is None:
            # 未命名文档：先保存再评测
            if not self.tabs.save_current():
                return
            path = self.tabs.current_path()
        if not path:
            return
        self.bottom_tabs.setCurrentWidget(self.cph_panel)
        self.bottom_tabs.setVisible(True)
        self.act_toggle_bottom.setChecked(True)
        self.cph_panel.run_all()

    def _save_current_quietly(self) -> None:
        # 评测前把编辑器中的最新代码落盘（已有路径时不弹对话框）
        if self.tabs.current_path() is not None:
            self.tabs.save_current()

    # ---- 字体缩放 --------------------------------------------------------
    FONT_SIZE_MIN = 8
    FONT_SIZE_MAX = 36
    FONT_SIZE_DEFAULT = 11

    def _zoom_font(self, delta: int) -> None:
        size = max(
            self.FONT_SIZE_MIN,
            min(self.FONT_SIZE_MAX, self.settings.font_size + delta),
        )
        if size == self.settings.font_size:
            return
        self.settings.font_size = size
        self.tabs.refresh_settings()
        self.terminal.set_font_size(size)
        self.statusBar().showMessage(f"字号：{size}", 1500)

    def _reset_font_size(self) -> None:
        self.settings.font_size = self.FONT_SIZE_DEFAULT
        self.tabs.refresh_settings()
        self.terminal.set_font_size(self.FONT_SIZE_DEFAULT)
        self.statusBar().showMessage(f"字号：{self.FONT_SIZE_DEFAULT}", 1500)

    # ---- 设置 ------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            # 先应用全局主题：setStyleSheet 触发的重抛光会用缓存 palette
            # 覆盖控件，因此编辑器配色必须在其后刷新
            apply_app_theme(QApplication.instance(), self.settings.highlight_style)
            self.tabs.refresh_settings()
            self.ai_sidebar.reload_client()
            self.ai_sidebar.refresh_models()
            self.lsp.reload()
            # 字体/高亮样式变化时同步终端
            self.terminal.apply_font(
                self.settings.font_family, self.settings.font_size
            )
            self.statusBar().showMessage("设置已保存", 3000)

    # ---- 终端 ------------------------------------------------------------
    def _restart_terminal(self) -> None:
        self.bottom_tabs.setCurrentWidget(self.terminal)
        self.terminal.restart_shell()

    def _on_bottom_tab_changed(self, index: int) -> None:
        if self.bottom_tabs.widget(index) is self.terminal:
            if not self.terminal.is_running():
                self.terminal.start_shell()
            # 切换到终端标签即把焦点送进终端，保证用户可以直接打字
            # （否则焦点停在标签栏，按键无法到达 Shell）
            self.terminal.setFocus()

    # ---- 标签/编辑器联动 --------------------------------------------------
    def _on_file_tracked(self, path: str) -> None:
        self.settings.add_recent_file(path)

    def _on_current_tab_changed(self, _index: int) -> None:
        editor = self.tabs.current_editor()
        self.find_bar.attach(editor)
        # 样例测试面板跟随当前文件
        self.cph_panel.bind(self.tabs.current_path())
        if editor is None:
            self.cursor_label.setText("无编辑器")
            return
        if id(editor) not in self._bound_editors:
            editor.cursorPositionChanged.connect(
                lambda _=None, e=editor: self._update_cursor_status(e)
            )
            editor.textChanged.connect(self._update_ai_context)
            self._bound_editors.add(id(editor))
        self._update_cursor_status(editor)
        self._update_ai_context()

    def _update_cursor_status(self, editor) -> None:
        if editor is not self.tabs.current_editor():
            return
        line, col = editor.cursor_position()
        path = self.tabs.path_for(editor)
        name = os.path.basename(path) if path else "未命名"
        self.cursor_label.setText(f"{name}  |  行 {line}, 列 {col}")

    def _update_ai_context(self, *_args) -> None:
        editor = self.tabs.current_editor()
        if editor is None:
            self.ai_sidebar.set_editor_context("", "", "")
            return
        path = self.tabs.path_for(editor) or ""
        name = os.path.basename(path) if path else "未命名"
        selection = editor.textCursor().selectedText()
        # QTextCursor.selectedText 用 U+2029 表示段落分隔
        selection = selection.replace("\u2029", "\n")
        self.ai_sidebar.set_editor_context(
            name, editor.toPlainText() if not selection else "", selection
        )

    # ---- LSP：编辑器/文件/诊断联动 ----------------------------------------
    def _on_editor_created(self, editor) -> None:
        editor.completion_controller = CompletionController(
            editor,
            self.lsp,
            path_provider=lambda e=editor: self.tabs.path_for(e),
        )
        editor.textChanged.connect(
            lambda _=None, e=editor: self._sync_editor_change_to_lsp(e)
        )

    def _sync_editor_change_to_lsp(self, editor) -> None:
        path = self.tabs.path_for(editor)
        if path:
            self.lsp.on_changed(path, editor.toPlainText())

    def _on_lsp_file_opened(self, path: str) -> None:
        editor = self.tabs.editor_for_path(path)
        self.lsp.on_opened(path, editor.toPlainText() if editor else "")

    def _on_lsp_file_saved(self, path: str, old_path: object) -> None:
        editor = self.tabs.editor_for_path(path)
        text = editor.toPlainText() if editor else ""
        old = str(old_path) if old_path else None
        if old and os.path.normcase(os.path.normpath(old)) != os.path.normcase(
            os.path.normpath(path)
        ):
            # 另存为到新路径：旧文档关闭、新文档打开
            self.lsp.on_closed(old)
            self.lsp.on_opened(path, text)
        elif old is None:
            # 未命名文档首次落盘
            self.lsp.on_opened(path, text)
        else:
            self.lsp.on_saved(path, text)

    def _on_lsp_diagnostics(self, path: str, diagnostics: list) -> None:
        editor = self.tabs.editor_for_path(path)
        if editor is not None:
            editor.set_diagnostics(diagnostics)
        total = self.problems_panel.update_file(path, diagnostics)
        index = self.bottom_tabs.indexOf(self.problems_panel)
        if index >= 0:
            self.bottom_tabs.setTabText(index, f"问题 ({total})" if total else "问题")

    def _on_lsp_server_status(self, key: str, message: str) -> None:
        self._lsp_server_messages[key] = message
        self.lsp_label.setText("LSP · " + " | ".join(self._lsp_server_messages.values()))

    def _goto_diagnostic_location(self, path: str, line: int, char: int) -> None:
        editor = self.tabs.editor_for_path(path)
        if editor is None:
            editor = self.tabs.open_file(path)
        if editor is None:
            return
        self.tabs.setCurrentWidget(editor)
        block = editor.document().findBlockByNumber(line)
        if block.isValid():
            cursor = QTextCursor(block)
            cursor.setPosition(block.position() + min(char, len(block.text())))
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
            editor.setFocus()

    def _goto_problem_in_current(self, forward: bool) -> None:
        editor = self.tabs.current_editor()
        if editor is None:
            return
        diag = editor.goto_next_diagnostic(forward)
        if diag is not None:
            source = f"[{diag.source}] " if diag.source else ""
            self.statusBar().showMessage(
                f"{diag.severity_label()}：{source}{diag.message}", 8000
            )
            editor.setFocus()
        else:
            self.statusBar().showMessage("当前文件没有问题", 4000)

    # ---- 最近打开 --------------------------------------------------------
    def _populate_recent(self) -> None:
        self.recent_menu.clear()
        files = self.settings.recent_files()
        if not files:
            empty = self.recent_menu.addAction("（无）")
            empty.setEnabled(False)
            return
        for path in files:
            act = self.recent_menu.addAction(path)
            act.triggered.connect(lambda _=False, p=path: self.tabs.open_file(p))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("清空列表")
        clear.triggered.connect(self.settings.clear_recent_files)

    # ---- 关于 ------------------------------------------------------------
    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 lime",
            "<b>lime</b> 1.0<br/>"
            "Python + PyQt6 构建的轻量代码编辑器<br/>"
            "语法高亮：Pygments · 实时解析/补全：LSP (clangd) · AI：本地 Ollama",
        )

    # ---- 窗口状态持久化 ---------------------------------------------------
    def _restore_state(self) -> None:
        geometry = self.settings.geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.window_state()
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.tabs.confirm_close_all():
            event.ignore()
            return
        self.settings.set_geometry(self.saveGeometry())
        self.settings.set_window_state(self.saveState())
        self.settings.sync()
        self.terminal.stop_shell()
        self.lsp.shutdown()
        event.accept()
