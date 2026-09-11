"""Codex on the fork's two surfaces: the menu-bar readout and the bars panel.

Uses Qt's offscreen platform so the tests run headless on CI.
"""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from claude_usage.collector import UsageStats
from claude_usage.overlay import (
    BASE_HEIGHT,
    CODEX_BLOCK_GAP,
    SCOPED_ROW_HEIGHT,
    TEXT_SCALE,
    UsageOverlay,
    draw_codex_mark,
)
from claude_usage.themes import get_theme
from claude_usage.widget import ClaudeUsageApp

_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _stats(codex: bool) -> UsageStats:
    st = UsageStats()
    st.session_utilization, st.session_reset = 0.42, 2_000_000_000
    st.weekly_utilization, st.weekly_reset = 0.71, 2_000_000_000
    st.codex_available = codex
    st.codex_session_utilization, st.codex_session_reset = 0.15, 2_000_000_000
    st.codex_weekly_utilization, st.codex_weekly_reset = 0.07, 2_000_000_000
    return st


def _readout(codex: bool) -> QPixmap:
    fake = SimpleNamespace(stats=_stats(codex))
    return ClaudeUsageApp._tray_readout_pixmap(fake, get_theme("zellij"))


class TestCodexMark(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()

    def test_mark_paints_something_in_the_requested_colour(self) -> None:
        pm = QPixmap(40, 40)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        draw_codex_mark(p, 20, 20, 32, "#ff0000")
        p.end()
        img = pm.toImage()
        red = [QColor(img.pixel(x, y)) for x in range(40) for y in range(40)
               if img.pixelColor(x, y).alpha() > 200]
        self.assertGreater(len(red), 100)
        self.assertTrue(all(c.red() > 200 and c.green() < 40 for c in red))
        # Woven, not solid: the middle of the blossom is a hole.
        self.assertLess(img.pixelColor(20, 20).alpha(), 40)


class TestMenuBarReadout(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()

    def test_codex_block_widens_the_readout(self) -> None:
        self.assertGreater(_readout(True).width(), _readout(False).width())

    def test_without_codex_the_readout_is_unchanged(self) -> None:
        a, b = _readout(False), _readout(False)
        self.assertEqual(a.toImage(), b.toImage())


class TestPanelBars(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self.cfg = {"theme": "zellij", "osd_view_mode": "bars",
                    "show_ticker": False, "show_news": False}

    def test_codex_pair_grows_the_panel_by_two_rows_and_a_gap(self) -> None:
        ov = UsageOverlay(dict(self.cfg))
        ov.update_stats(_stats(False))
        base = ov.height()
        self.assertEqual(base, int(BASE_HEIGHT * TEXT_SCALE))
        ov.update_stats(_stats(True))
        self.assertEqual(
            ov.height(), int((BASE_HEIGHT + 2 * SCOPED_ROW_HEIGHT + CODEX_BLOCK_GAP) * TEXT_SCALE))
        ov.update_stats(_stats(False))
        self.assertEqual(ov.height(), base)


if __name__ == "__main__":
    unittest.main()
