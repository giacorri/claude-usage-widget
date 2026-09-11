"""Pace: is a window being spent faster than the clock that empties it?

The bar colour says how much is gone. Pace says whether that is a lot *for
this point in the window*: 80% with 45 minutes left of a 5-hour window is
fine, 80% on the Wednesday of a weekly window that started Monday noon is
not. The comparison is "used" against "expected", where expected is the
share of the window's time that has already gone by.

For the 5-hour window that share is wall-clock time. For the weekly window
only working time counts: with the default Mon-Fri 9-18 a window that opens
Monday noon has spent ~13% of its working hours by Monday evening and ~93%
by Friday evening, so the weekend and the evenings do not silently push the
expectation up while nothing is being used. Empty ``pace_work_days`` falls
back to wall-clock, which is also what an all-day, all-week setting yields.

Pure module — no GUI, no clock of its own (the caller passes ``now``), and
config read off a plain dict with ``.get`` like ``peak``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

SESSION_WINDOW_SECONDS = 5 * 3600
WEEKLY_WINDOW_SECONDS = 7 * 86400

# The level compares what is left of the budget with what is left of the
# window: ``(1 - used) / (1 - expected)`` is 1.0 when the remaining budget
# covers the remaining time at the window's average rate. Ratios rather than
# a flat margin because the same five points are nothing on a Monday and the
# whole of Monday morning on a Friday night.
PACE_OK_RATIO = 0.95     # at least 95% of what the rest of the window needs
PACE_WARN_RATIO = 0.70   # runs out in the last 30% of the remaining time

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_CRIT = "crit"


def _working_seconds(
    start: datetime, end: datetime, days: frozenset[int], day_start: float, day_end: float,
) -> float:
    """Seconds of working time in [start, end], with working days/hours in local time."""
    if end <= start:
        return 0.0
    total = 0.0
    day = start.date()
    while day <= end.date():
        if day.weekday() in days:
            midnight = datetime.combine(day, datetime.min.time())
            lo = max(start, midnight + timedelta(hours=day_start))
            hi = min(end, midnight + timedelta(hours=day_end))
            if hi > lo:
                total += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return total


def expected_fraction(
    now: float,
    reset_ts: int,
    window_seconds: int,
    config: dict | None = None,
    *,
    working_hours: bool = False,
) -> float:
    """Share (0.0-1.0) of the window ending at ``reset_ts`` that has elapsed.

    ``working_hours`` switches from wall-clock to the working time defined by
    ``pace_work_days`` (``datetime.weekday()`` values, default Mon-Fri) and
    ``pace_work_start_hour`` / ``pace_work_end_hour`` (default 9-18, local).
    """
    if not reset_ts or window_seconds <= 0:
        return 0.0
    start_ts = reset_ts - window_seconds
    if now <= start_ts:
        return 0.0
    if now >= reset_ts:
        return 1.0

    if working_hours:
        cfg = config or {}
        days = frozenset(int(d) for d in (cfg.get("pace_work_days") or []))
        day_start = float(cfg.get("pace_work_start_hour", 9))
        day_end = float(cfg.get("pace_work_end_hour", 18))
        if days and day_end > day_start:
            start = datetime.fromtimestamp(start_ts)
            end = datetime.fromtimestamp(reset_ts)
            total = _working_seconds(start, end, days, day_start, day_end)
            if total > 0:
                done = _working_seconds(start, datetime.fromtimestamp(now), days, day_start, day_end)
                return max(0.0, min(1.0, done / total))

    return (now - start_ts) / window_seconds


def pace_level(used: float, expected: float) -> str:
    """LEVEL_OK / LEVEL_WARN / LEVEL_CRIT for ``used`` against ``expected``.

    A window already at 100% is critical whatever the clock says: there is
    nothing left to pace. Past the end of the window nothing more is needed,
    so anything short of 100% is fine.
    """
    if used >= 1.0:
        return LEVEL_CRIT
    left = 1.0 - used
    need = 1.0 - expected
    if need <= 0.0 or left >= need * PACE_OK_RATIO:
        return LEVEL_OK
    if left >= need * PACE_WARN_RATIO:
        return LEVEL_WARN
    return LEVEL_CRIT
