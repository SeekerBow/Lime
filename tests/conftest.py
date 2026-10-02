"""pytest 全局夹具：offscreen QApplication 与临时 IniFormat 配置。"""

import os
import sys

import pytest

# 必须在导入 QApplication 前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from lime.core.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(["pytest-lime"])
    yield app


@pytest.fixture
def settings(tmp_path):
    qs = QSettings(str(tmp_path / "lime-test.ini"), QSettings.Format.IniFormat)
    return Settings(qs)


def pump(ms: int = 50) -> None:
    """驱动事件循环若干毫秒（信号/进程输出落地）。"""
    QTest.qWait(ms)


def wait_for(predicate, timeout_ms: int = 15000, step_ms: int = 50) -> bool:
    """轮询直到 predicate 为真或超时，返回最终结果。"""
    elapsed = 0
    while elapsed < timeout_ms:
        pump(step_ms)
        if predicate():
            return True
        elapsed += step_ms
    return predicate()


def run_event_loop_until(signal, timeout_ms: int = 15000) -> None:
    """运行事件循环直到信号触发或超时。"""
    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
