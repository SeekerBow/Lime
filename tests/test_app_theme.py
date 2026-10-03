# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""全局应用主题测试：配色方案应驱动整个窗口的调色板。"""

from __future__ import annotations

from PyQt6.QtGui import QPalette

from lime.editor.tab_manager import TabManager
from lime.editor.themes import is_dark
from lime.ui.app_theme import (
    apply_app_theme,
    build_theme_palette,
    theme_colors,
    theme_stylesheet,
)


def test_dark_style_drives_dark_palette():
    colors = theme_colors("one-dark-pro")
    assert colors["background"].lower() == "#282c34"
    assert colors["foreground"].lower() == "#abb2bf"

    pal = build_theme_palette("one-dark-pro")
    assert pal.color(QPalette.ColorRole.Base).name().lower() == "#282c34"
    assert pal.color(QPalette.ColorRole.Text).name().lower() == "#abb2bf"
    # 窗口外围与内容区色调不同，形成层次
    window = pal.color(QPalette.ColorRole.Window).name().lower()
    assert window != "#282c34"
    assert is_dark(window)
    # 选择高亮取自样式的 highlight_color
    assert pal.color(QPalette.ColorRole.Highlight).name().lower() == "#3a3f4b"
    assert theme_stylesheet("one-dark-pro").strip() != ""


def test_builtin_style_with_empty_token_color_falls_back():
    # pygments "default" 样式的根前景为空，应按背景亮度回退
    colors = theme_colors("default")
    assert colors["background"]
    assert colors["foreground"]
    assert colors["accent"]
    pal = build_theme_palette("default")
    assert pal.color(QPalette.ColorRole.Base).name().lower() == colors[
        "background"
    ].lower()


def test_light_style_keeps_light_text_scheme():
    colors = theme_colors("default")
    assert not is_dark(colors["background"])
    pal = build_theme_palette("default")
    # 浅色主题：文本为深色、窗口仍为浅色
    assert not is_dark(pal.color(QPalette.ColorRole.Window).name())
    assert is_dark(pal.color(QPalette.ColorRole.Text).name())


def test_disabled_and_placeholder_roles_derived():
    pal = build_theme_palette("one-dark-pro")
    disabled_text = pal.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
    )
    normal_text = pal.color(QPalette.ColorRole.Text)
    assert disabled_text != normal_text
    placeholder = pal.color(QPalette.ColorRole.PlaceholderText)
    assert placeholder != normal_text


def test_editor_background_switches_on_theme_toggle(qapp, settings):
    # 回归：全局 setStyleSheet 重抛光时不能打回深色缓存
    tabs = TabManager(settings)
    ed = tabs.new_document()
    def base(widget):
        return widget.palette().color(QPalette.ColorRole.Base).name().lower()
    for _ in range(2):
        settings.highlight_style = "one-dark-pro"
        apply_app_theme(qapp, settings.highlight_style)
        tabs.refresh_settings()
        assert base(ed) == "#282c34"
        assert base(ed.viewport()) == "#282c34"
        settings.highlight_style = "default"
        apply_app_theme(qapp, settings.highlight_style)
        tabs.refresh_settings()
        assert base(ed) == "#f8f8f8"
        assert base(ed.viewport()) == "#f8f8f8"
