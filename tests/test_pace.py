"""Pace: the share of a window that has gone by, and the level it earns.

The weekly cases use a window opening Monday 2026-09-07 12:00 local — the
shape the working-hours model is built for — and the readout cases check
that the countdown, not the percentage, is what takes the colour.
"""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from datetime import datetime
from types import SimpleNamespace

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from claude_usage.collector import UsageStats
from claude_usage.pace import (
    LEVEL_CRIT,
    LEVEL_OK,
    LEVEL_WARN,
    SESSION_WINDOW_SECONDS,
    WEEKLY_WINDOW_SECONDS,
    expected_fraction,
    pace_level,
)
from claude_usage.themes import get_theme
from claude_usage.widget import ClaudeUsageApp

_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _ts(spec: str) -> float:
    return datetime.strptime(spec, "%Y-%m-%d %H:%M").timestamp()


# Monday noon → next Monday noon. Mon-Fri 9-18 gives 6 + 4×9 + 3 = 45 working hours.
MON_NOON = _ts("2026-09-07 12:00")
WEEK_RESET = int(MON_NOON + WEEKLY_WINDOW_SECONDS)
WORK_CFG = {"pace_work_days": [0, 1, 2, 3, 4],
            "pace_work_start_hour": 9, "pace_work_end_hour": 18}


class TestSessionWindow(unittest.TestCase):
    """The 5h window paces on wall-clock time."""

    def test_linear(self) -> None:
        reset = 2_000_000_000
        now = reset - 45 * 60
        got = expected_fraction(now, reset, SESSION_WINDOW_SECONDS)
        self.assertAlmostEqual(got, 1 - 45 / 300, places=6)

    def test_clamped_to_the_window(self) -> None:
        reset = 2_000_000_000
        self.assertEqual(expected_fraction(reset - SESSION_WINDOW_SECONDS - 5, reset,
                                           SESSION_WINDOW_SECONDS), 0.0)
        self.assertEqual(expected_fraction(reset + 5, reset, SESSION_WINDOW_SECONDS), 1.0)

    def test_no_reset_means_nothing_elapsed(self) -> None:
        self.assertEqual(expected_fraction(1.0, 0, SESSION_WINDOW_SECONDS), 0.0)


class TestWeeklyWindowWorkingHours(unittest.TestCase):
    def expected(self, spec: str, cfg: dict = WORK_CFG) -> float:
        return expected_fraction(_ts(spec), WEEK_RESET, WEEKLY_WINDOW_SECONDS, cfg,
                                 working_hours=True)

    def test_monday_evening_is_half_a_day(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-07 18:00"), 6 / 45, places=6)

    def test_nothing_moves_overnight(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-07 23:00"), self.expected("2026-09-08 08:00"))

    def test_wednesday_evening_is_about_half(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-09 18:00"), 24 / 45, places=6)

    def test_friday_evening_leaves_only_monday_morning(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-11 18:00"), 42 / 45, places=6)

    def test_weekend_does_not_count(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-13 15:00"), 42 / 45, places=6)

    def test_all_gone_at_the_reset(self) -> None:
        self.assertAlmostEqual(self.expected("2026-09-14 12:00"), 1.0)
        self.assertAlmostEqual(self.expected("2026-09-14 10:30"), 43.5 / 45, places=6)

    def test_no_work_days_falls_back_to_wall_clock(self) -> None:
        cfg = dict(WORK_CFG, pace_work_days=[])
        self.assertAlmostEqual(self.expected("2026-09-09 18:00", cfg), 2.25 / 7, places=6)

    def test_all_week_all_day_is_wall_clock(self) -> None:
        cfg = {"pace_work_days": list(range(7)),
               "pace_work_start_hour": 0, "pace_work_end_hour": 24}
        self.assertAlmostEqual(self.expected("2026-09-09 18:00", cfg), 2.25 / 7, places=6)


class TestPaceLevel(unittest.TestCase):
    def test_under_the_clock_is_ok(self) -> None:
        self.assertEqual(pace_level(0.80, 0.85), LEVEL_OK)

    def test_a_little_ahead_early_on_is_still_ok(self) -> None:
        # 3% in the first working hour: one big prompt, not a runaway.
        self.assertEqual(pace_level(0.03, 0.01), LEVEL_OK)

    def test_ahead_is_warn(self) -> None:
        self.assertEqual(pace_level(0.60, 0.53), LEVEL_WARN)

    def test_far_ahead_is_crit(self) -> None:
        self.assertEqual(pace_level(0.70, 0.53), LEVEL_CRIT)

    def test_friday_night_with_monday_morning_to_go(self) -> None:
        # Reset Monday noon: 42 of 45 working hours gone, Monday morning
        # still needs ~7%. 91% leaves 9%: fine. 95% leaves 5%: short.
        # 97% leaves 3%: gone by mid-morning.
        friday = 42 / 45
        self.assertEqual(pace_level(0.91, friday), LEVEL_OK)
        self.assertEqual(pace_level(0.95, friday), LEVEL_WARN)
        self.assertEqual(pace_level(0.97, friday), LEVEL_CRIT)

    def test_exhausted_is_crit_even_at_the_end(self) -> None:
        self.assertEqual(pace_level(1.0, 0.99), LEVEL_CRIT)

    def test_past_the_end_anything_left_is_ok(self) -> None:
        self.assertEqual(pace_level(0.99, 1.0), LEVEL_OK)


def _readout(pace: bool, used: float, remaining_seconds: int) -> QPixmap:
    st = UsageStats()
    now = datetime.now().timestamp()
    st.session_utilization = used
    st.session_reset = int(now + remaining_seconds)
    # Weekly pinned red on both bar and countdown (90% with the whole week
    # ahead), so the ok colour can only come from the session countdown.
    st.weekly_utilization, st.weekly_reset = 0.9, int(now + WEEKLY_WINDOW_SECONDS)
    fake = SimpleNamespace(stats=st, config={"pace_colors": pace})
    return ClaudeUsageApp._tray_readout_pixmap(fake, get_theme("zellij"))


def _hues(pm: QPixmap) -> set[tuple[int, int, int]]:
    img = pm.toImage()
    return {QColor(img.pixel(x, y)).getRgb()[:3]
            for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).alpha() > 250}


class TestMenuBarCountdownColour(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self.theme = get_theme("zellij")

    def _has(self, pm: QPixmap, key: str) -> bool:
        return QColor(self.theme[key]).getRgb()[:3] in _hues(pm)

    def test_on_pace_countdown_takes_the_ok_colour(self) -> None:
        # 80% used, 45 min of 5h left: the bar is red, the countdown is not.
        pm = _readout(True, 0.80, 45 * 60)
        self.assertTrue(self._has(pm, "bar_blue"))
        self.assertTrue(self._has(pm, "crit"))

    def test_ahead_of_the_clock_countdown_goes_red(self) -> None:
        # 80% gone after one hour: the bar is red and so is the countdown,
        # and only the digits stay white — the ok colour is nowhere.
        pm = _readout(True, 0.80, 4 * 3600)
        self.assertTrue(self._has(pm, "crit"))
        self.assertFalse(self._has(pm, "bar_blue"))

    def test_switched_off_the_readout_is_the_old_one(self) -> None:
        pm = _readout(False, 0.80, 45 * 60)
        self.assertFalse(self._has(pm, "bar_blue"))


if __name__ == "__main__":
    unittest.main()
