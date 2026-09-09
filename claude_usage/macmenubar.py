"""Native macOS menu-bar item.

Qt's :class:`QSystemTrayIcon` asks the icon for a *square* the height of the
menu bar, so a wide readout comes back scaled to a few pixels tall and the
numbers are unreadable — which is why this bypasses it and drives an
``NSStatusItem`` directly. The item shows the two bars as its image and the
two percentages as coloured text beside them, and clicking it pops the same
Qt menu the OSD's right-click uses, so there is only ever one menu to maintain.

Import is guarded: without PyObjC the caller falls back to the Qt tray icon.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QBuffer, QByteArray, QPoint
from PySide6.QtGui import QPixmap

try:  # pragma: no cover - exercised only on macOS with PyObjC installed
    import objc
    from AppKit import (
        NSApp,
        NSEventMaskLeftMouseDown,
        NSEventMaskRightMouseDown,
        NSColor,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSImage,
        NSMutableAttributedString,
        NSScreen,
        NSStatusBar,
        NSVariableStatusItemLength,
    )
    from Foundation import NSData, NSObject
    AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS, or PyObjC missing
    AVAILABLE = False


if AVAILABLE:

    class _ClickTarget(NSObject):
        """Target for the status button's action.

        AppKit needs an ObjC object to send the action to; the Python callback
        rides along on an attribute rather than through init, because PyObjC
        initialisers have to be declared selector-side.
        """

        def initWithHandler_(self, handler):  # noqa: N802
            self = objc.super(_ClickTarget, self).init()
            if self is None:
                return None
            self._handler = handler
            return self

        def statusItemClicked_(self, sender):  # noqa: N802, ARG002
            self._handler()


def _ns_image(pixmap: QPixmap) -> Any:
    """Convert a QPixmap to an NSImage at its device-independent size."""
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    raw = bytes(data)
    img = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
    size = pixmap.deviceIndependentSize()
    img.setSize_((size.width(), size.height()))
    img.setTemplate_(False)
    return img


def _ns_color(hex_color: str) -> Any:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)


class MacMenuBarItem:
    """An NSStatusItem whose click opens *menu* (a QMenu)."""

    def __init__(self, on_menu: Callable[[QPoint], None]) -> None:
        self._on_menu = on_menu
        self._item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        self._target = _ClickTarget.alloc().initWithHandler_(self._clicked)
        button = self._item.button()
        button.setTarget_(self._target)
        button.setAction_("statusItemClicked:")
        button.setImagePosition_(2)  # NSImageLeft
        # Both buttons open the menu; a status button is sent only
        # left-mouse-up by default, so the right one has to be asked for.
        button.sendActionOn_(NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown)

    def _clicked(self) -> None:
        """Pop the Qt menu just under the status item — either mouse button."""
        button = self._item.button()
        window = button.window()
        frame = window.frame()
        # Cocoa screen coordinates start bottom-left on the main screen; Qt's
        # global coordinates start top-left, so the y needs flipping against
        # the screen that carries the menu bar (always screens()[0]).
        screen_height = NSScreen.screens()[0].frame().size.height
        NSApp.activateIgnoringOtherApps_(True)
        self._on_menu(QPoint(int(frame.origin.x), int(screen_height - frame.origin.y)))

    def set_readout(self, pixmap: QPixmap) -> None:
        """Show *pixmap* as the item's whole content.

        The caller paints bars and text together, so there is no title: an
        NSImage sized explicitly is left at that size, which is what makes a
        wide readout survive up here.
        """
        self._item.button().setImage_(_ns_image(pixmap))

    def dispose(self) -> None:
        NSStatusBar.systemStatusBar().removeStatusItem_(self._item)
