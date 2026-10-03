# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""filebrowser.file_browser 单元测试。"""

import os

import pytest

from lime.filebrowser.file_browser import FileBrowser


@pytest.fixture
def browser(qapp, settings, tmp_path):
    b = FileBrowser(settings)
    b.set_root(str(tmp_path))
    return b, tmp_path


def test_set_root(browser, settings):
    b, root = browser
    assert b.root_path() == str(root)
    assert os.path.normcase(settings.last_dir) == os.path.normcase(str(root))


def test_create_file_emits_open_on_double_click(browser):
    b, root = browser
    path = b.create_file("open_me.py")
    assert os.path.isfile(path)

    opened = []
    b.file_open_requested.connect(opened.append)
    index = b.model.index(path)
    b._on_double_clicked(index)
    assert len(opened) == 1
    assert os.path.normcase(os.path.normpath(opened[0])) == os.path.normcase(
        os.path.normpath(path)
    )


def test_double_click_folder_no_signal(browser):
    b, root = browser
    folder = b.create_folder("sub")
    opened = []
    b.file_open_requested.connect(opened.append)
    b._on_double_clicked(b.model.index(folder))
    assert opened == []


def test_create_folder_and_file_inside(browser):
    b, root = browser
    folder = b.create_folder("pkg")
    path = b.create_file("mod.py", target_dir=folder)
    assert os.path.isfile(path)


def test_create_file_existing_raises(browser):
    b, root = browser
    b.create_file("dup.txt")
    with pytest.raises(FileExistsError):
        b.create_file("dup.txt")


def test_rename_selected(browser):
    b, root = browser
    path = b.create_file("old.txt")
    b.tree.setCurrentIndex(b.model.index(path))
    assert b.rename_selected("new.txt") is True
    assert os.path.isfile(root / "new.txt")
    assert not os.path.exists(path)


def test_delete_selected_file(browser):
    b, root = browser
    path = b.create_file("trash.txt")
    b.tree.setCurrentIndex(b.model.index(path))
    assert b.delete_selected() is True
    assert not os.path.exists(path)


def test_delete_selected_folder(browser):
    b, root = browser
    folder = b.create_folder("trashdir")
    b.tree.setCurrentIndex(b.model.index(folder))
    assert b.delete_selected() is True
    assert not os.path.exists(folder)


def test_no_root_errors(browser, settings):
    b = FileBrowser(settings)
    with pytest.raises(ValueError):
        b.create_file("x.txt")
