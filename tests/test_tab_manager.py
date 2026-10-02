"""editor.tab_manager 单元测试。"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from lime.editor import tab_manager as tab_module
from lime.editor.tab_manager import TabManager


@pytest.fixture
def manager(qapp, settings):
    return TabManager(settings)


def test_new_document(manager):
    editor = manager.new_document()
    assert manager.count() == 1
    assert manager.current_editor() is editor
    assert "未命名" in manager.tabText(0)
    assert manager.current_path() is None


def test_open_file(manager, tmp_path):
    path = tmp_path / "hello.py"
    path.write_text("print('hi')", encoding="utf-8")
    editor = manager.open_file(str(path))
    assert editor is not None
    assert manager.count() == 1
    assert manager.tabText(0) == "hello.py"
    assert manager.current_path().endswith("hello.py")
    assert editor.toPlainText() == "print('hi')"
    assert editor.highlighter.lexer() is not None


def test_open_same_file_reuses_tab(manager, tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    manager.new_document()
    manager.open_file(str(path))
    manager.open_file(str(path))
    assert manager.count() == 2  # 一个未命名 + 一个文件，文件不重复


def test_dirty_marker_and_save(manager, tmp_path):
    path = tmp_path / "dirty.py"
    path.write_text("", encoding="utf-8")
    editor = manager.open_file(str(path))
    editor.insertPlainText("changed")
    assert manager.is_modified() is True
    assert manager.tabText(0).startswith("• ")

    assert manager.save_current() is True
    assert path.read_text(encoding="utf-8") == "changed"
    assert manager.is_modified() is False
    assert not manager.tabText(0).startswith("•")


def test_save_as(manager, tmp_path):
    manager.new_document()
    editor = manager.current_editor()
    editor.setPlainText("data")

    target = tmp_path / "out.txt"
    # 绕过文件对话框，直接走保存实现
    assert manager._save_to_path(editor, str(target)) is True
    assert target.read_text(encoding="utf-8") == "data"
    assert manager.current_path() == str(target)


def test_close_unmodified_tab(manager):
    manager.new_document()
    assert manager.close_tab(0) is True
    assert manager.count() == 0


def test_close_modified_tab_discard(manager, monkeypatch):
    manager.new_document()
    manager.current_editor().insertPlainText("unsaved")
    monkeypatch.setattr(
        tab_module.QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Discard,
    )
    assert manager.close_tab(0) is True
    assert manager.count() == 0


def test_close_modified_tab_cancel(manager, monkeypatch):
    manager.new_document()
    manager.current_editor().insertPlainText("unsaved")
    monkeypatch.setattr(
        tab_module.QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Cancel,
    )
    assert manager.close_tab(0) is False
    assert manager.count() == 1


def test_close_modified_tab_save(manager, tmp_path, monkeypatch):
    path = tmp_path / "x.py"
    path.write_text("", encoding="utf-8")
    manager.open_file(str(path))
    manager.current_editor().insertPlainText("v2")

    monkeypatch.setattr(
        tab_module.QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Save,
    )
    assert manager.close_tab(0) is True
    assert path.read_text(encoding="utf-8") == "v2"


def test_refresh_settings_applies(manager, settings):
    manager.new_document()
    settings.font_size = 18
    settings.highlight_style = "monokai"
    manager.refresh_settings()
    assert manager.current_editor().font().pointSize() == 18
    assert manager.current_editor().highlighter.style_name == "monokai"
