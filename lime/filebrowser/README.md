# lime.filebrowser — 文件浏览器

基于 `QFileSystemModel + QTreeView` 的目录树面板。

## `FileBrowser(QWidget)`

- `set_root(path)`：展开根目录并写入 `settings.last_dir`；
- 信号 `file_open_requested(str)`：双击文件时发出（文件夹不发）；
- 文件操作（不依赖 GUI 对话框，便于脚本/测试调用）：
  - `create_file(name, target_dir=None)`
  - `create_folder(name, target_dir=None)`
  - `rename_selected(new_name)`
  - `delete_selected()`（目录递归删除）
- 右键菜单提供上述操作的交互入口（名称通过 `QInputDialog` 获取）；
- `selected_path()` 返回当前选中的完整路径。

主窗口把 `file_open_requested` 连接到 `TabManager.open_file`。

## 测试

`tests/test_file_browser.py`：根目录设置、双击信号（文件 vs 文件夹）、
新建/重命名/删除文件与文件夹、重名报错、未打开根目录时报错。
