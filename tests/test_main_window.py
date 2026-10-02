"""ui.main_window 集成测试：菜单、联动、布局、关闭持久化。"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from lime.editor import tab_manager as tab_module
from lime.ui.main_window import MainWindow


@pytest.fixture
def window(qapp, settings):
    win = MainWindow(settings)
    return win


def test_starts_with_one_document(window):
    assert window.tabs.count() == 1
    assert "lime" in window.windowTitle()


def test_window_uses_application_icon(qapp):
    from lime.app import application_icon

    icon = application_icon()
    assert not icon.isNull()
    assert icon.availableSizes()  # ico 内含多种尺寸


def test_actions_have_shortcuts(window):
    assert "CTRL" in window.act_new.shortcut().toString().upper()
    assert "CTRL" in window.act_save.shortcut().toString().upper()
    assert window.act_run.shortcut().toString() == "F5"
    assert "CTRL" in window.act_find.shortcut().toString().upper()


def test_open_file_via_file_browser_signal(window, tmp_path):
    path = tmp_path / "proj" / "main.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('abc abc')", encoding="utf-8")

    window.file_browser.set_root(str(tmp_path))
    window.file_browser._on_double_clicked(window.file_browser.model.index(str(path)))

    assert window.tabs.count() == 2
    assert window.tabs.current_path() == str(path)
    assert window.ai_sidebar.editor_context().filename == "main.py"


def test_find_bar_finds_in_current_editor(window, tmp_path):
    path = tmp_path / "f.py"
    path.write_text("abc abc", encoding="utf-8")
    window.tabs.open_file(str(path))

    assert window.find_bar.isHidden() is True
    window.act_find.trigger()
    assert window.find_bar.isHidden() is False
    window.find_bar.find_input.setText("abc")
    assert "匹配 2 处" in window.find_bar.count_label.text()
    assert window.find_bar.find_next() is True


def test_view_toggles(window):
    window.act_toggle_ai.setChecked(False)
    assert window.ai_sidebar.isHidden() is True
    window.act_toggle_files.setChecked(False)
    assert window.file_browser.isHidden() is True
    window.act_toggle_bottom.setChecked(False)
    assert window.bottom_tabs.isHidden() is True


def test_cursor_status_updates(window):
    editor = window.tabs.current_editor()
    editor.setPlainText("line1\nline2")
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    assert "行 2" in window.cursor_label.text()


def test_run_unsaved_prompts_save_cancel(window, monkeypatch):
    # 另存为对话框被取消 -> 不运行
    monkeypatch.setattr(
        window.tabs,
        "save_current",
        lambda: False,
    )
    assert window.tabs.current_path() is None
    window.run_current()
    assert window.output_panel.runner.is_running() is False


def test_close_unmodified_saves_geometry(window, settings):
    window.tabs.current_editor().setPlainText("")
    window.close()
    settings.sync()
    assert settings.geometry() is not None


def test_close_modified_discard(window, monkeypatch):
    window.tabs.current_editor().insertPlainText("dirty")
    monkeypatch.setattr(
        tab_module.QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Discard,
    )
    window.close()
    assert window.terminal.is_running() is False


def test_close_modified_cancel_keeps_open(window, monkeypatch):
    window.tabs.current_editor().insertPlainText("dirty")
    monkeypatch.setattr(
        tab_module.QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Cancel,
    )
    window.close()
    assert window.tabs.count() == 1


def test_recent_files_tracked(window, tmp_path):
    path = tmp_path / "recent.py"
    path.write_text("x = 1", encoding="utf-8")
    window.tabs.open_file(str(path))
    assert str(path) in window.settings.recent_files()
