"""The menu-bar readout fitting the room the bar has.

Uses Qt's offscreen platform so the tests run headless on CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from itertools import pairwise
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from claude_usage import menubar_space
from claude_usage.collector import UsageStats
from claude_usage.themes import get_theme
from claude_usage.widget import ClaudeUsageApp

_app: QApplication | None = None

FULL, COMPACT, NUMBERS = (
    (True, True, False, False), (False, True, False, False), (False, False, False, False))
COMPACT_ALT, NUMBERS_ALT = (False, True, True, False), (False, False, True, False)


def _small(rung: tuple) -> tuple:
    return (*rung[:3], True)


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _fake(codex: bool, **config) -> SimpleNamespace:
    st = UsageStats()
    st.session_utilization, st.session_reset = 0.42, 2_000_000_000
    st.weekly_utilization, st.weekly_reset = 0.71, 2_000_000_000
    st.codex_available = codex
    st.codex_session_utilization, st.codex_session_reset = 0.15, 2_000_000_000
    st.codex_weekly_utilization, st.codex_weekly_reset = 0.07, 2_000_000_000
    return SimpleNamespace(stats=st, config={"pace_colors": True, **config})


def _blocks(codex: bool) -> list:
    return ClaudeUsageApp._readout_blocks(_fake(codex))


class TestRungWidths(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()

    def test_dropping_bars_then_countdowns_narrows_the_readout(self) -> None:
        for codex in (False, True):
            blocks = _blocks(codex)
            full, compact, numbers = (
                ClaudeUsageApp._rung_width(blocks, r) for r in (FULL, COMPACT, NUMBERS))
            self.assertGreater(full, compact)
            self.assertGreater(compact, numbers)

    def test_taking_turns_narrows_it_further(self) -> None:
        blocks = _blocks(codex=True)
        for both, turns in ((COMPACT, COMPACT_ALT), (NUMBERS, NUMBERS_ALT)):
            self.assertGreater(ClaudeUsageApp._rung_width(blocks, both),
                               ClaudeUsageApp._rung_width(blocks, turns))

    def test_the_smaller_font_narrows_every_shape(self) -> None:
        blocks = _blocks(codex=True)
        for rung in (FULL, COMPACT, NUMBERS, COMPACT_ALT, NUMBERS_ALT):
            self.assertGreater(ClaudeUsageApp._rung_width(blocks, rung),
                               ClaudeUsageApp._rung_width(blocks, _small(rung)))

    def test_alternating_is_as_wide_as_the_wider_provider(self) -> None:
        blocks = _blocks(codex=True)
        singles = [ClaudeUsageApp._readout_width([b], bars=False, countdown=True)
                   for b in blocks]
        self.assertEqual(ClaudeUsageApp._rung_width(blocks, COMPACT_ALT), max(singles))

    def test_painted_width_matches_the_measured_one(self) -> None:
        fake = _fake(codex=False)
        theme = get_theme("zellij")
        for bars, countdown in ((True, True), (False, True), (False, False)):
            for small in (False, True):
                pm = ClaudeUsageApp._tray_readout_pixmap(
                    fake, theme, bars=bars, countdown=countdown, small=small)
                self.assertEqual(
                    pm.deviceIndependentSize().width(),
                    ClaudeUsageApp._readout_width(
                        _blocks(False), bars=bars, countdown=countdown, small=small))

    def test_min_width_pads_so_the_two_turns_share_one_width(self) -> None:
        fake = _fake(codex=True)
        blocks = _blocks(codex=True)
        width = ClaudeUsageApp._rung_width(blocks, COMPACT_ALT)
        sizes = {
            ClaudeUsageApp._tray_readout_pixmap(
                fake, get_theme("zellij"), bars=False, blocks=[b], min_width=width,
            ).deviceIndependentSize().width()
            for b in blocks
        }
        self.assertEqual(sizes, {width})


class TestPickingTheRung(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()

    def _pick(self, codex: bool, budget, **config) -> tuple[bool, bool, bool, bool]:
        fake = _fake(codex, **config)
        return ClaudeUsageApp._pick_readout_rung(fake, _blocks(codex), budget)

    def test_room_for_everything_keeps_the_full_readout(self) -> None:
        self.assertEqual(self._pick(True, 10_000), FULL)

    def test_no_budget_means_the_full_readout(self) -> None:
        self.assertEqual(self._pick(True, None), FULL)

    def test_the_widest_rung_under_the_budget_wins(self) -> None:
        # Which rung is next narrowest depends on the countdown text, so
        # the ladder is read off the measured widths rather than assumed.
        blocks = _blocks(codex=True)
        shapes = (FULL, COMPACT, NUMBERS, COMPACT_ALT, NUMBERS_ALT)
        rungs = shapes + tuple(_small(r) for r in shapes)
        ladder = sorted(rungs, key=lambda r: -ClaudeUsageApp._rung_width(blocks, r))
        for wider, narrower in pairwise(ladder):
            budget = ClaudeUsageApp._rung_width(blocks, wider) - 1
            self.assertEqual(self._pick(True, budget), narrower)

    def test_nothing_fits_takes_the_narrowest(self) -> None:
        self.assertEqual(self._pick(True, 1), _small(NUMBERS_ALT))
        self.assertEqual(self._pick(False, 1), _small(NUMBERS))

    def test_one_provider_never_alternates(self) -> None:
        numbers = ClaudeUsageApp._rung_width(_blocks(False), _small(NUMBERS))
        self.assertEqual(self._pick(False, numbers - 1), _small(NUMBERS))

    def test_a_pinned_layout_ignores_the_budget(self) -> None:
        self.assertEqual(self._pick(True, 1, menubar_layout="full"), FULL)
        self.assertEqual(self._pick(True, 1, menubar_layout="compact"), COMPACT)
        self.assertEqual(self._pick(True, 10_000, menubar_layout="numbers"), NUMBERS)


def _win(x, w, *, layer=25, y=0, h=33, pid=1):
    return {"kCGWindowLayer": layer, "kCGWindowOwnerPID": pid,
            "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h}}


class TestOccupiedWidth(unittest.TestCase):
    def test_counts_only_status_windows_in_the_bar_right_of_the_region(self) -> None:
        windows = [
            _win(1254, 38), _win(1292, 36), _win(1370, 144),  # the system's items
            _win(400, 47),                                    # left of the notch
            _win(1300, 80, pid=42),                           # ours, as our window
            _win(0, 1512, layer=24),                          # the bar itself
            _win(1430, 72, y=916, h=56),                      # a panel, not an item
        ]
        self.assertEqual(
            menubar_space.occupied_width(
                windows, region_left=850, own_pid=42, own_width=None, bar_height=32),
            38 + 36 + 144)

    def test_a_hosted_item_of_our_width_is_ours_and_skipped_once(self) -> None:
        # Three items the host owns, two of them as wide as ours: one is
        # ours, the other is somebody else's and still counts.
        windows = [_win(906, 47), _win(953, 105), _win(1058, 105), _win(1254, 38)]
        self.assertEqual(
            menubar_space.occupied_width(
                windows, region_left=850, own_pid=42, own_width=105, bar_height=32),
            47 + 105 + 38)

    def test_no_status_window_at_all_means_unobservable(self) -> None:
        # macOS 27: the bar is one window below the status level and the
        # items are not listed, so "nothing taken" would be a lie.
        windows = [_win(0, 1512, layer=24), _win(1430, 72, y=916, h=56)]
        self.assertIsNone(
            menubar_space.occupied_width(
                windows, region_left=850, own_pid=42, own_width=None, bar_height=32))

    def test_only_our_own_window_is_still_an_observed_bar(self) -> None:
        self.assertEqual(
            menubar_space.occupied_width(
                [_win(1300, 80, pid=42)], region_left=850, own_pid=42,
                own_width=None, bar_height=32),
            0.0)


class TestBudgetFor(unittest.TestCase):
    def test_observed_bar_subtracts_items_and_margin(self) -> None:
        self.assertEqual(
            menubar_space.budget_for(660, 300, {"menubar_reserve": 20}),
            660 - 300 - 20 - menubar_space.ITEM_PADDING)

    def test_unobserved_bar_scales_with_the_region(self) -> None:
        # macOS 27: the same assumption leaves a notched 14" tight and an
        # external display wide, instead of one fixed width for both.
        notch = menubar_space.budget_for(660, None, {})
        external = menubar_space.budget_for(1960, None, {})
        self.assertLess(notch, 270)
        self.assertEqual(external - notch, 1300)
