# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""全局应用主题：把编辑器的 Pygments 配色方案扩展到整个程序窗口。

从所选样式推导 :class:`QPalette`，配合 Fusion 风格让菜单栏、文件浏览器、
输出/终端面板、AI 侧栏、对话框等与编辑器保持同一配色。
"""

from __future__ import annotations

from pygments.token import Name, Operator, Token

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from ..editor.themes import get_style, is_dark, mix_color


def _parse_color(value: str | None) -> str | None:
    """从 Pygments 样式串（如 ``italic #5c6370``、``bg:#e06c75``）提取颜色。"""
    if not value:
        return None
    for part in value.split():
        if part.startswith("bg:#"):
            return part[3:]
        if part.startswith("#") and len(part) >= 4:
            return part
    return None


def theme_colors(style_name: str) -> dict[str, str]:
    """从 Pygments 样式推导全局主题色（六键色板）。"""
    style_cls = get_style(style_name)
    styles: dict = getattr(style_cls, "styles", {}) or {}

    background = (getattr(style_cls, "background_color", "") or "").strip()
    if not background:
        background = "#ffffff"
    foreground = _parse_color(styles.get(Token, ""))
    if foreground is None:
        foreground = "#e6e6e6" if is_dark(background) else "#1f1f1f"
    accent = (
        _parse_color(styles.get(Name.Function, ""))
        or _parse_color(styles.get(Operator, ""))
        or foreground
    )
    highlight = (getattr(style_cls, "highlight_color", "") or "").strip()
    if not highlight:
        highlight = mix_color(background, foreground, 0.2)
    return {
        "background": background,
        "foreground": foreground,
        "accent": accent,
        "highlight": highlight,
    }


def build_theme_palette(style_name: str) -> QPalette:
    """把样式色板映射为应用级 QPalette。"""
    c = theme_colors(style_name)
    bg, fg, accent, highlight = (
        c["background"], c["foreground"], c["accent"], c["highlight"],
    )
    dark = is_dark(bg)

    # 窗口外围比内容区更深一档，形成层次；按钮向前景方向微调
    window_bg = mix_color(bg, "#000000", 0.16 if dark else 0.05)
    button_bg = mix_color(bg, fg, 0.08)
    base_bg = bg
    alternate_bg = mix_color(base_bg, window_bg, 0.5)
    tooltip_bg = mix_color(window_bg, fg, 0.08)
    disabled = mix_color(fg, bg, 0.55)
    placeholder = mix_color(fg, bg, 0.45)

    def col(value: str) -> QColor:
        return QColor(value)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, col(window_bg))
    pal.setColor(QPalette.ColorRole.WindowText, col(fg))
    pal.setColor(QPalette.ColorRole.Base, col(base_bg))
    pal.setColor(QPalette.ColorRole.AlternateBase, col(alternate_bg))
    pal.setColor(QPalette.ColorRole.Text, col(fg))
    pal.setColor(QPalette.ColorRole.Button, col(button_bg))
    pal.setColor(QPalette.ColorRole.ButtonText, col(fg))
    pal.setColor(QPalette.ColorRole.ToolTipBase, col(tooltip_bg))
    pal.setColor(QPalette.ColorRole.ToolTipText, col(fg))
    pal.setColor(QPalette.ColorRole.BrightText, col("#ffffff" if dark else "#000000"))
    pal.setColor(QPalette.ColorRole.Highlight, col(highlight))
    pal.setColor(QPalette.ColorRole.HighlightedText, col(fg))
    pal.setColor(QPalette.ColorRole.Link, col(accent))
    pal.setColor(QPalette.ColorRole.LinkVisited, col(mix_color(accent, bg, 0.35)))
    pal.setColor(QPalette.ColorRole.PlaceholderText, col(placeholder))
    accent_role = getattr(QPalette.ColorRole, "AccentColor", None)
    if accent_role is not None:
        pal.setColor(accent_role, col(accent))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        pal.setColor(QPalette.ColorGroup.Disabled, role, col(disabled))
    pal.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Highlight,
        col(mix_color(highlight, bg, 0.5)),
    )
    return pal


def theme_stylesheet(style_name: str) -> str:
    """极简全局样式表：只补调色板覆盖不到的细节。"""
    c = theme_colors(style_name)
    return (
        f"QToolTip {{ background-color: {mix_color(c['background'], c['foreground'], 0.08)};"
        f" color: {c['foreground']};"
        f" border: 1px solid {c['accent']}; padding: 2px; }}"
    )


def apply_app_theme(app: QApplication, style_name: str) -> None:
    """把配色方案应用到整个应用（Fusion 风格保证色板全平台生效）。"""
    app.setStyle("Fusion")
    app.setPalette(build_theme_palette(style_name))
    app.setStyleSheet(theme_stylesheet(style_name))
