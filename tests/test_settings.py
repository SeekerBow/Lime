# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""core.settings 单元测试。"""

from PyQt6.QtCore import QByteArray, QSettings

from lime.core.settings import Settings


def test_defaults(settings):
    assert settings.font_size == 11
    assert settings.tab_width == 4
    assert settings.spaces_instead_of_tabs is True
    assert settings.line_numbers is True
    assert settings.ollama_host == "http://127.0.0.1:11434"
    assert settings.terminal_shell == ""


def test_set_get_typed(settings):
    settings.font_size = 14
    settings.tab_width = 2
    settings.font_family = "Cascadia Code"
    assert settings.font_size == 14
    assert settings.tab_width == 2
    assert settings.font_family == "Cascadia Code"


def test_bool_roundtrip(tmp_path):
    ini = tmp_path / "a.ini"
    s1 = Settings(QSettings(str(ini), QSettings.Format.IniFormat))
    s1.line_numbers = False
    s1.word_wrap = True
    s1.sync()

    # 用全新的 QSettings 读回，验证确实持久化
    s2 = Settings(QSettings(str(ini), QSettings.Format.IniFormat))
    assert s2.line_numbers is False
    assert s2.word_wrap is True


def test_host_trailing_slash_stripped(settings):
    settings.ollama_host = "http://127.0.0.1:11434/"
    assert settings.ollama_host == "http://127.0.0.1:11434"


def test_recent_files_dedupe_and_cap(settings):
    for i in range(12):
        settings.add_recent_file(f"/tmp/f{i}.py")
    files = settings.recent_files()
    assert len(files) == Settings.MAX_RECENT
    assert files[0] == "/tmp/f11.py"

    # 再次打开已存在的文件，置顶且不重复
    settings.add_recent_file("/tmp/f5.py")
    files = settings.recent_files()
    assert files[0] == "/tmp/f5.py"
    assert files.count("/tmp/f5.py") == 1

    settings.clear_recent_files()
    assert settings.recent_files() == []


def test_geometry_roundtrip(settings):
    assert settings.geometry() is None
    settings.set_geometry(QByteArray(b"abc123"))
    assert bytes(settings.geometry()) == b"abc123"
