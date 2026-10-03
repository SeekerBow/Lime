# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""ui.main_window 集成测试：菜单、联动、布局、关闭持久化。"""

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest

from lime.editor import tab_manager as tab_module
from lime.ui.main_window import MainWindow
from tests.conftest import wait_for


@pytest.fixture
def window(qapp, settings, monkeypatch):
    # MainWindow 创建 AI 侧边栏时会异步发起真实网络请求拉取模型列表，
    # 测试中禁掉，避免后台 QThread 在窗口回收时引发崩溃
    from lime.ai.ai_sidebar import AISidebar

    monkeypatch.setattr(AISidebar, "refresh_models", lambda self: None)
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


def test_zoom_actions_have_expected_shortcuts(window):
    in_keys = [s.toString() for s in window.act_zoom_in.shortcuts()]
    out_keys = [s.toString() for s in window.act_zoom_out.shortcuts()]
    assert any("Up" in s for s in in_keys)
    assert any("=" in s or "+" in s for s in in_keys)
    assert any("Down" in s for s in out_keys)
    assert any("-" in s for s in out_keys)


def test_zoom_in_out_changes_editor_and_terminal_font(window, settings):
    start = settings.font_size
    window._zoom_font(+1)
    assert settings.font_size == start + 1
    assert window.tabs.current_editor().font().pointSize() == start + 1
    assert window.terminal.input_edit.font().pointSize() == start + 1

    window._zoom_font(-1)
    assert settings.font_size == start
    assert window.tabs.current_editor().font().pointSize() == start


def test_zoom_clamped_to_bounds(window, settings):
    for _ in range(100):
        window._zoom_font(+1)
    assert settings.font_size == MainWindow.FONT_SIZE_MAX
    for _ in range(100):
        window._zoom_font(-1)
    assert settings.font_size == MainWindow.FONT_SIZE_MIN


def test_zoom_reset_restores_default(window, settings):
    window._zoom_font(+3)
    window._reset_font_size()
    assert settings.font_size == MainWindow.FONT_SIZE_DEFAULT
    assert window.tabs.current_editor().font().pointSize() == MainWindow.FONT_SIZE_DEFAULT


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


def test_switching_to_terminal_tab_starts_shell_and_focuses(window):
    # 回归：只点击“终端”标签头就应能直接打字——
    # 切到终端标签时必须启动 Shell 并把焦点送进终端控件
    window.show()
    QTest.qWait(100)
    try:
        assert window.terminal.is_running() is False
        window.bottom_tabs.setCurrentWidget(window.terminal)
        QTest.qWait(500)
        assert window.terminal.is_running() is True
        # 焦点落在终端底部的命令输入框中
        assert QApplication.focusWidget() is window.terminal.input_edit
    finally:
        window.terminal.stop_shell()


def test_run_unsaved_creates_temp_cpp_and_runs(window, monkeypatch, tmp_path):
    # 未命名文档直接写入临时文件运行，不打断用户
    editor = window.tabs.current_editor()
    editor.setPlainText("int main(){ return 0; }\n")
    assert window.tabs.current_path() is None
    window.run_current()
    assert window.output_panel.runner.is_running() is True
    # 等待运行结束（编译+空输入直接结束）
    wait_for(lambda: not window.output_panel.runner.is_running())
    # 退出码 0 表示编译和运行都成功
    assert "[已结束，退出码 0]" in window.output_panel.output_view.toPlainText()


def test_run_unsaved_no_editor_does_nothing(window):
    # 没有编辑器时不报错也不运行
    window.tabs.close_tab(0)
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
