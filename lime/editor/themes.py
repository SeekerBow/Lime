"""lime 内置的自定义 Pygments 主题与主题注册表。

Pygments 自带 50 种样式（one-dark、nord、dracula 等），这里补充几款
流行的编辑器配色（**One Dark Pro**、Tokyo Night、Catppuccin Mocha、
GitHub Dark Dimmed），并提供统一的 :func:`get_style` 入口与配色工具。
"""

from __future__ import annotations

from pygments.style import Style
from pygments.styles import get_all_styles, get_style_by_name
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Token,
)

# --------------------------------------------------------------------------
# One Dark Pro（VS Code 最流行的深色主题之一）
# --------------------------------------------------------------------------
class OneDarkProStyle(Style):
    background_color = "#282c34"
    highlight_color = "#3a3f4b"
    line_number_color = "#5c6370"
    styles = {
        Token: "#abb2bf",
        Comment: "italic #5c6370",
        Comment.Preproc: "#c678dd",
        Comment.PreprocFile: "#98c379",
        Keyword: "#c678dd",
        Operator: "#56b6c2",
        Operator.Word: "#c678dd",
        Punctuation: "#abb2bf",
        Name.Function: "#61afef",
        Name.Function.Magic: "#61afef",
        Name.Class: "#e5c07b",
        Name.Builtin: "#56b6c2",
        Name.Builtin.Pseudo: "italic #e06c75",
        Name.Decorator: "#61afef",
        Name.Constant: "#d19a66",
        Name.Attribute: "#e06c75",
        Name.Exception: "#e5c07b",
        Name.Tag: "#e06c75",
        Number: "#d19a66",
        String: "#98c379",
        String.Escape: "#56b6c2",
        String.Interpol: "#e06c75",
        Generic.Heading: "bold #e5c07b",
        Generic.Subheading: "bold #61afef",
        Error: "#ffffff bg:#e06c75",
    }


# --------------------------------------------------------------------------
# Tokyo Night
# --------------------------------------------------------------------------
class TokyoNightStyle(Style):
    background_color = "#1a1b26"
    highlight_color = "#2e3246"
    line_number_color = "#565f89"
    styles = {
        Token: "#a9b1d6",
        Comment: "italic #565f89",
        Comment.Preproc: "#bb9af7",
        Comment.PreprocFile: "#9ece6a",
        Keyword: "#bb9af7",
        Operator: "#89ddff",
        Operator.Word: "#bb9af7",
        Punctuation: "#a9b1d6",
        Name.Function: "#7aa2f7",
        Name.Function.Magic: "#7aa2f7",
        Name.Class: "#2ac3de",
        Name.Builtin: "#7dcfff",
        Name.Builtin.Pseudo: "italic #f7768e",
        Name.Decorator: "#7aa2f7",
        Name.Constant: "#ff9e64",
        Name.Attribute: "#73daca",
        Name.Exception: "#e0af68",
        Name.Tag: "#f7768e",
        Number: "#ff9e64",
        String: "#9ece6a",
        String.Escape: "#89ddff",
        String.Interpol: "#f7768e",
        Generic.Heading: "bold #e0af68",
        Generic.Subheading: "bold #7aa2f7",
        Error: "#ffffff bg:#f7768e",
    }


# --------------------------------------------------------------------------
# Catppuccin Mocha
# --------------------------------------------------------------------------
class CatppuccinMochaStyle(Style):
    background_color = "#1e1e2e"
    highlight_color = "#313244"
    line_number_color = "#6c7086"
    styles = {
        Token: "#cdd6f4",
        Comment: "italic #6c7086",
        Comment.Preproc: "#cba6f7",
        Comment.PreprocFile: "#a6e3a1",
        Keyword: "#cba6f7",
        Operator: "#89dceb",
        Operator.Word: "#cba6f7",
        Punctuation: "#cdd6f4",
        Name.Function: "#89b4fa",
        Name.Function.Magic: "#89b4fa",
        Name.Class: "#f9e2af",
        Name.Builtin: "#94e2d5",
        Name.Builtin.Pseudo: "italic #f38ba8",
        Name.Decorator: "#89b4fa",
        Name.Constant: "#fab387",
        Name.Attribute: "#74c7ec",
        Name.Exception: "#f9e2af",
        Name.Tag: "#f38ba8",
        Number: "#fab387",
        String: "#a6e3a1",
        String.Escape: "#89dceb",
        String.Interpol: "#f5c2e7",
        Generic.Heading: "bold #f9e2af",
        Generic.Subheading: "bold #89b4fa",
        Error: "#ffffff bg:#f38ba8",
    }


# --------------------------------------------------------------------------
# GitHub Dark Dimmed
# --------------------------------------------------------------------------
class GitHubDarkDimmedStyle(Style):
    background_color = "#22272e"
    highlight_color = "#2d333b"
    line_number_color = "#768390"
    styles = {
        Token: "#adbac7",
        Comment: "italic #768390",
        Comment.Preproc: "#f47067",
        Comment.PreprocFile: "#96d0ff",
        Keyword: "#f47067",
        Operator: "#f69d50",
        Operator.Word: "#f47067",
        Punctuation: "#adbac7",
        Name.Function: "#dcbdfb",
        Name.Function.Magic: "#dcbdfb",
        Name.Class: "#f69d50",
        Name.Builtin: "#dcbdfb",
        Name.Builtin.Pseudo: "italic #f69d50",
        Name.Decorator: "#6cb6ff",
        Name.Constant: "#6cb6ff",
        Name.Attribute: "#6cb6ff",
        Name.Exception: "#f69d50",
        Name.Tag: "#8ddb8c",
        Number: "#6cb6ff",
        String: "#96d0ff",
        String.Escape: "#f69d50",
        String.Interpol: "#f47067",
        Generic.Heading: "bold #f69d50",
        Generic.Subheading: "bold #dcbdfb",
        Error: "#ffffff bg:#f47067",
    }


#: 自定义样式名 -> 样式类
CUSTOM_STYLES: dict[str, type[Style]] = {
    "one-dark-pro": OneDarkProStyle,
    "tokyo-night": TokyoNightStyle,
    "catppuccin-mocha": CatppuccinMochaStyle,
    "github-dark-dimmed": GitHubDarkDimmedStyle,
}

#: 全部可选样式（内置 + 自定义），自定义排前面方便选择
AVAILABLE_STYLE_NAMES: tuple[str, ...] = tuple(
    sorted(CUSTOM_STYLES) + sorted(s for s in get_all_styles() if s not in CUSTOM_STYLES)
)


def get_style(name: str) -> type[Style]:
    """先查自定义注册表，再回退到 Pygments 内置样式。"""
    cls = CUSTOM_STYLES.get(name)
    if cls is not None:
        return cls
    return get_style_by_name(name)


# --------------------------------------------------------------------------
# 配色工具
# --------------------------------------------------------------------------
def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = (color or "#000000").strip().lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    try:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix_color(first: str, second: str, t: float) -> str:
    """按比例 ``t`` 把 ``first`` 混向 ``second``（0=first，1=second）。"""
    a = hex_to_rgb(first)
    b = hex_to_rgb(second)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def is_dark(color: str) -> bool:
    """按感知亮度判断是否为深色背景。"""
    r, g, b = hex_to_rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140
