"""How much of the menu bar the readout may take.

macOS hides a status item outright when the bar is full, and since macOS 26
the item is rendered out of process (``NSSceneStatusItem``): the app is told
nothing — its button window keeps a placeholder frame, ``isVisible`` stays
true, placed or not. So there is nothing to ask after the fact; the budget
is computed up front from what *is* observable:

* the screen that carries the menu bar, and on a notched one the area to the
  right of the notch (``auxiliaryTopRightArea``) — status items never go
  left of it;
* every item currently on screen, which the window list does report: the
  system's own and, on macOS 26, other apps' too, all as Control Center's
  windows at the status-bar level. Ours is among them and is told apart by
  its width, since the owner is Control Center rather than us.

Import is guarded like ``macmenubar``: without PyObjC there is no budget and
the caller keeps the full readout.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

try:  # pragma: no cover - macOS with PyObjC only
    from AppKit import NSScreen
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListOptionOnScreenOnly,
    )
    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False

# Window level of status items (NSStatusWindowLevel).
_STATUS_LEVEL = 25
# A status item's window is its image plus this much, both sides together —
# measured on macOS 26, not documented.
ITEM_PADDING = 4.0


def occupied_width(
    windows: Iterable[dict[str, Any]], *, region_left: float, own_pid: int,
    own_width: float | None, bar_height: float,
) -> float:
    """Sum of the widths of the status-level windows sitting in the menu bar
    right of *region_left*, other than our own.

    Ours is skipped by owner where the item is the app's own window, and
    otherwise by width — the first window as wide as *own_width* — since
    a hosted item's window belongs to the host.
    """
    total = 0.0
    own_seen = own_width is None
    for w in windows:
        if w.get("kCGWindowLayer") != _STATUS_LEVEL:
            continue
        if w.get("kCGWindowOwnerPID") == own_pid:
            continue
        b = w.get("kCGWindowBounds") or {}
        y, h, x = float(b.get("Y", -1)), float(b.get("Height", 0)), float(b.get("X", 0))
        if y != 0 or h > bar_height * 2 or x < region_left:
            continue
        width = float(b.get("Width", 0))
        if not own_seen and abs(width - own_width) <= 1.0:
            own_seen = True
            continue
        total += width
    return total


def readout_budget(config: dict[str, Any], own_image_width: float | None) -> float | None:
    """Points the readout image may be wide, or None when unknowable.

    *own_image_width* is what the item shows now, so its own room is not
    counted against it.
    """
    if not AVAILABLE:
        return None
    screens = NSScreen.screens()
    if not screens:
        return None
    screen = screens[0]  # the one with the menu bar
    frame = screen.frame()
    # A struct, so "no notch" comes back as an empty rect rather than None.
    area = screen.auxiliaryTopRightArea() if hasattr(screen, "auxiliaryTopRightArea") else None
    if area is not None and float(area.size.width) > 0:
        region_left = float(area.origin.x)
        region_width = float(area.size.width)
        bar_height = float(area.size.height)
    else:
        # No notch: the app menu sets the left edge and changes with every
        # app switch, so it is an allowance rather than a measurement.
        region_left = float(config.get("menubar_app_menu_width", 600))
        region_width = float(frame.size.width) - region_left
        bar_height = 24.0
    windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    taken = occupied_width(
        windows, region_left=region_left, own_pid=os.getpid(),
        own_width=None if own_image_width is None else own_image_width + ITEM_PADDING,
        bar_height=bar_height)
    reserve = float(config.get("menubar_reserve", 0))
    return region_width - taken - reserve - ITEM_PADDING
