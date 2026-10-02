"""基于 LSP 的智能补全：无焦点弹窗 + 编辑器控制器。

- :class:`CompletionPopup`：ToolTip 型无焦点列表，位置跟随光标
- :class:`CompletionController`：打字防抖、触发字符、候选项过滤、
  键盘导航与文本插入
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from .protocol import CompletionItem

#: 标识符前缀（含 C++ 的 :: / . / -> 之后的成员名，取最后一段标识符）
_PREFIX_RE = re.compile(r"[A-Za-z_$][\w$]*$")
_SNIPPET_ARG = re.compile(r"\$\{\d+:?(.*?)\}", re.DOTALL)
_SNIPPET_NUM = re.compile(r"\$\d+")

#: 输入后多久发起补全（毫秒）
COMPLETION_DEBOUNCE_MS = 120
MAX_ITEMS = 60


def strip_snippets(text: str) -> str:
    """把残留的 LSP snippet 占位符（``${1:x}``/``$0``）展平。"""
    text = _SNIPPET_ARG.sub(r"\1", text)
    text = _SNIPPET_NUM.sub("", text)
    return text


def current_prefix(editor) -> str:
    """光标前的标识符前缀。"""
    cursor = editor.textCursor()
    text = cursor.block().text()[: cursor.positionInBlock()]
    match = _PREFIX_RE.search(text)
    return match.group(0) if match else ""


def filter_items(items: list[CompletionItem], prefix: str) -> list[CompletionItem]:
    """按前缀过滤排序：精确前缀（大小写敏感）→ 忽略大小写 → 包含。"""
    if not prefix:
        return items[:MAX_ITEMS]
    exact: list[CompletionItem] = []
    ci_prefix: list[CompletionItem] = []
    fuzzy: list[CompletionItem] = []
    low = prefix.lower()
    for item in items:
        label = item.label
        if label.startswith(prefix):
            exact.append(item)
        elif label.lower().startswith(low):
            ci_prefix.append(item)
        elif low in label.lower():
            fuzzy.append(item)
    return (exact + ci_prefix + fuzzy)[:MAX_ITEMS]


def apply_completion(editor, item: CompletionItem, prefix: str) -> None:
    """把候选项写入编辑器：优先用 textEdit 范围，否则替换前缀。"""
    new_text = strip_snippets(item.insert_value)
    cursor = editor.textCursor()

    if item.text_edit is not None:
        edit = item.text_edit
        document = editor.document()
        start_block = document.findBlockByNumber(edit.start_line)
        end_block = document.findBlockByNumber(edit.end_line)
        if start_block.isValid():
            if not end_block.isValid():
                end_block = start_block
            start = start_block.position() + min(edit.start_char, len(start_block.text()))
            end = end_block.position() + min(edit.end_char, len(end_block.text()))
            cursor.setPosition(start)
            cursor.setPosition(max(start, end), QTextCursor.MoveMode.KeepAnchor)
    elif prefix:
        # 回退方案：删掉刚输入的前缀再插入
        for _ in prefix:
            cursor.deletePreviousChar()
    cursor.insertText(new_text)
    editor.setTextCursor(cursor)


class CompletionPopup(QListWidget):
    """无焦点补全列表窗，显示在编辑器之上，不抢夺键盘焦点。"""

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self._editor = editor
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setAlternatingRowColors(True)
        self.itemClicked.connect(lambda _item: self.accept_current())

    def show_items(self, items: list[CompletionItem]) -> None:
        self.clear()
        for item in items:
            text = item.label
            if item.detail:
                text += f"    {item.detail}"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.addItem(list_item)
        if self.count():
            self.setCurrentRow(0)
        self._reposition()
        self.show()
        self.raise_()

    def _reposition(self) -> None:
        rect = self._editor.cursorRect()
        pos = self._editor.mapToGlobal(rect.bottomLeft())
        self.setFixedWidth(max(320, min(560, self._editor.width() - 40)))
        row_hint = self.sizeHintForRow(0) if self.count() else 22
        self.setFixedHeight(min(240, max(72, self.count() * (row_hint or 22) + 8)))
        screen = self.screen() or self._editor.screen()
        if screen is not None:
            available = screen.availableGeometry()
            if pos.x() + self.width() > available.right():
                pos.setX(available.right() - self.width() - 4)
            if pos.y() + self.height() > available.bottom() - 8:
                above = self._editor.mapToGlobal(rect.topLeft())
                pos.setY(above.y() - self.height() - 2)
        self.move(pos)

    def move_selection(self, delta: int) -> None:
        if not self.count():
            return
        row = (self.currentRow() + delta) % self.count()
        self.setCurrentRow(row)
        self.scrollToItem(self.currentItem())

    def current_item(self) -> Optional[CompletionItem]:
        item = self.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def accept_current(self) -> None:
        item = self.current_item()
        if item is not None:
            apply_completion(self._editor, item, getattr(self, "_active_prefix", ""))
        self.hide()


class CompletionController(QObject):
    """把编辑器、:class:`LspService` 与弹窗串起来。"""

    def __init__(
        self,
        editor,
        service,
        path_provider: Callable[[], Optional[str]],
    ) -> None:
        super().__init__(editor)
        self.editor = editor
        self.service = service
        self._path_provider = path_provider
        self.popup = CompletionPopup(editor)
        self._request_id = -1
        self._prefix = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.trigger(force=False))

        editor.textChanged.connect(self._on_text_changed)
        editor.cursorPositionChanged.connect(self._on_cursor_moved)
        service.completionReceived.connect(self._on_completions)

    # ---- 触发 ------------------------------------------------------------
    def _on_text_changed(self) -> None:
        if not self.popup.isVisible():
            self._timer.start(COMPLETION_DEBOUNCE_MS)
        else:
            # 弹窗已开：缩短延迟，让列表随打字即时收窄
            self._timer.start(40)

    def _on_cursor_moved(self) -> None:
        if not self.popup.isVisible():
            return
        # 光标移出当前单词所在行则关闭
        cursor = self.editor.textCursor()
        text_before = cursor.block().text()[: cursor.positionInBlock()]
        if not _PREFIX_RE.search(text_before):
            self.popup.hide()

    def trigger(self, force: bool = False) -> None:
        path = self._path_provider()
        if not path:
            self.popup.hide()
            return
        cursor = self.editor.textCursor()
        self._prefix = current_prefix(self.editor)
        text_before = cursor.block().text()[: cursor.positionInBlock()]
        triggers = self.service.trigger_characters(path)
        last_char = text_before[-1:] if text_before else ""
        if not force and not self._prefix and last_char not in triggers:
            self.popup.hide()
            return
        req_id = self.service.request_completion(
            path, cursor.blockNumber(), cursor.positionInBlock()
        )
        if req_id < 0:
            # 服务器尚未就绪：不打扰用户
            self.popup.hide()
            return
        self._request_id = req_id

    def _on_completions(self, request_id: int, items: list) -> None:
        if request_id != self._request_id:
            return
        filtered = filter_items(items, self._prefix)
        self.popup._active_prefix = self._prefix
        if not filtered:
            self.popup.hide()
            return
        self.popup.show_items(filtered)

    # ---- 键盘 ------------------------------------------------------------
    def handle_key_press(self, event) -> bool:
        """弹窗可见时拦截导航/确认键；返回 True 表示事件已消费。"""
        if not self.popup.isVisible():
            if event.key() == Qt.Key.Key_Down and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.trigger(force=True)
                return True
            return False
        key = event.key()
        if key in (Qt.Key.Key_Down,):
            self.popup.move_selection(1)
            return True
        if key == Qt.Key.Key_Up:
            self.popup.move_selection(-1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self.popup.accept_current()
            return True
        if key == Qt.Key.Key_Escape:
            self.popup.hide()
            return True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Space,
                   Qt.Key.Key_Home, Qt.Key.Key_End):
            # 这些键会改变补全语义；先关弹窗，交还给编辑器
            self.popup.hide()
            return False
        return False

    def hide(self) -> None:
        self.popup.hide()
