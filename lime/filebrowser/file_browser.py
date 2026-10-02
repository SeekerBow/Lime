"""文件浏览器：基于 :class:`QFileSystemModel` 的目录树。

支持选择根目录、双击打开文件（通过信号交给主窗口）以及
新建文件/文件夹、重命名、删除。
"""

from __future__ import annotations

import os

from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtCore import QDir, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings


class FileBrowser(QWidget):
    """左侧文件浏览器面板。"""

    #: 用户请求打开某个文件
    file_open_requested = pyqtSignal(str)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._root_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.open_button = QPushButton("打开文件夹")
        self.open_button.clicked.connect(self.choose_folder)
        self.root_label = QLabel("未打开文件夹")
        self.root_label.setStyleSheet("color: #666;")
        bar.addWidget(self.open_button)
        bar.addWidget(self.root_label, 1)
        layout.addLayout(bar)

        self.model = QFileSystemModel(self)
        self.model.setIconProvider(QFileIconProvider())
        self.model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs
        )

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(False)
        self.tree.header().setSectionResizeMode(  # type: ignore[union-attr]
            0, QHeaderView.ResizeMode.Stretch
        )
        for section in range(1, 4):
            self.tree.header().hideSection(section)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.tree)

    # ---- 根目录 ----------------------------------------------------------
    def choose_folder(self) -> None:
        start = self._root_path or self.settings.last_dir or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", start)
        if path:
            self.set_root(path)

    def set_root(self, path: str) -> None:
        if not path or not os.path.isdir(path):
            return
        self._root_path = os.path.abspath(path)
        self.model.setRootPath(self._root_path)
        self.tree.setRootIndex(self.model.index(self._root_path))
        self.root_label.setText(self._root_path)
        self.settings.last_dir = self._root_path

    def root_path(self) -> str:
        return self._root_path

    # ---- 打开文件 --------------------------------------------------------
    def _on_double_clicked(self, index) -> None:
        if index.isValid() and not self.model.isDir(index):
            path = self.model.filePath(index)
            if path:
                self.file_open_requested.emit(path)

    def selected_path(self) -> str:
        index = self.tree.currentIndex()
        return self.model.filePath(index) if index.isValid() else ""

    # ---- 新建/重命名/删除 -------------------------------------------------
    def _target_dir(self) -> str:
        index = self.tree.currentIndex()
        if index.isValid():
            path = self.model.filePath(index)
            if self.model.isDir(index):
                return path
            parent = os.path.dirname(path)
            if parent:
                return parent
        return self._root_path

    def create_file(self, name: str, target_dir: str | None = None) -> str:
        """在目标目录（默认选中目录/根目录）新建空文件，返回完整路径。"""
        base = target_dir or self._target_dir()
        if not base:
            raise ValueError("尚未打开任何文件夹")
        path = os.path.join(base, name)
        if os.path.exists(path):
            raise FileExistsError(path)
        with open(path, "w", encoding="utf-8"):
            pass
        self._refresh_dir(base)
        return path

    def create_folder(self, name: str, target_dir: str | None = None) -> str:
        base = target_dir or self._target_dir()
        if not base:
            raise ValueError("尚未打开任何文件夹")
        path = os.path.join(base, name)
        os.makedirs(path, exist_ok=False)
        self._refresh_dir(base)
        return path

    def rename_selected(self, new_name: str) -> bool:
        index = self.tree.currentIndex()
        if not index.isValid() or not new_name:
            return False
        ok = self.model.setData(index, new_name)
        if not ok:
            # 某些后端不支持 setData，退回 rename
            old = self.model.filePath(index)
            os.replace(old, os.path.join(os.path.dirname(old), new_name))
        self._refresh_dir(self._root_path)
        return True

    def delete_selected(self) -> bool:
        index = self.tree.currentIndex()
        if not index.isValid():
            return False
        import shutil

        path = self.model.filePath(index)
        if self.model.isDir(index):
            shutil.rmtree(path)
        else:
            os.remove(path)
        self._refresh_dir(self._root_path)
        return True

    def _refresh_dir(self, path: str) -> None:
        # QFileSystemModel 会监听文件变化，这里再主动 fetch 一次保证刷新
        index = self.model.index(path)
        if index.isValid():
            self.model.fetchMore(index)

    # ---- 右键菜单 --------------------------------------------------------
    def _show_context_menu(self, pos) -> None:
        if not self._root_path:
            return
        menu = QMenu(self)
        act_new_file = menu.addAction("新建文件")
        act_new_folder = menu.addAction("新建文件夹")
        menu.addSeparator()
        act_rename = menu.addAction("重命名")
        act_delete = menu.addAction("删除")

        has_selection = self.tree.currentIndex().isValid()
        act_rename.setEnabled(has_selection)
        act_delete.setEnabled(has_selection)

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action == act_new_file:
            name, ok = QInputDialog.getText(self, "新建文件", "文件名：")
            if ok and name:
                try:
                    self.create_file(name)
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(self, "新建文件失败", str(exc))
        elif action == act_new_folder:
            name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名：")
            if ok and name:
                try:
                    self.create_folder(name)
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(self, "新建文件夹失败", str(exc))
        elif action == act_rename:
            old = os.path.basename(self.selected_path())
            name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=old)
            if ok and name:
                try:
                    self.rename_selected(name)
                except OSError as exc:
                    QMessageBox.warning(self, "重命名失败", str(exc))
        elif action == act_delete:
            answer = QMessageBox.question(
                self, "删除", f"确定删除 “{os.path.basename(self.selected_path())}” 吗？"
            )
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.delete_selected()
                except OSError as exc:
                    QMessageBox.warning(self, "删除失败", str(exc))
