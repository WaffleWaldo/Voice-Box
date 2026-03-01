"""Floating overlay widget using GTK4 + gtk4-layer-shell.

Shows a dark pill-shaped widget at the bottom of the screen with:
- Live audio waveform during recording
- Spinning arc during processing
- Green checkmark on completion
- Red X on error

Never steals focus — uses layer-shell OVERLAY layer with no keyboard interactivity.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from enum import Enum, auto

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import GLib, Gtk, Gdk, Gtk4LayerShell  # noqa: E402

log = logging.getLogger(__name__)

# Layout constants
_PILL_HEIGHT = 56
_RECORDING_WIDTH = 280
_CIRCLE_SIZE = 56
_BOTTOM_MARGIN = 48

# Colors
_BG = (0.0, 0.0, 0.0, 1.0)  # solid black
_WHITE = (1.0, 1.0, 1.0)
_GREEN = (0.290, 0.855, 0.502)  # #4ade80
_RED = (0.965, 0.376, 0.376)  # #f66060

# Waveform
_NUM_BARS = 32
_BAR_WIDTH = 4
_BAR_GAP = 3
_BAR_MIN_H = 4
_BAR_MAX_H = 36

# Animation
_SPINNER_FPS_INTERVAL = 16  # ~60fps


class _Mode(Enum):
    HIDDEN = auto()
    RECORDING = auto()
    PROCESSING = auto()
    DONE = auto()
    ERROR = auto()


class Overlay:
    """Thread-safe overlay widget. All public methods use GLib.idle_add internally."""

    def __init__(self, app: Gtk.Application) -> None:
        self._app = app
        self._mode = _Mode.HIDDEN
        self._levels: deque[float] = deque([0.0] * _NUM_BARS, maxlen=_NUM_BARS)
        self._spinner_angle = 0.0
        self._spinner_timer: int | None = None
        self._hide_timer: int | None = None

        self._window = Gtk.Window(application=app)
        self._window.set_decorated(False)
        self._window.set_resizable(False)

        # Layer-shell setup
        Gtk4LayerShell.init_for_window(self._window)
        Gtk4LayerShell.set_layer(self._window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(
            self._window, Gtk4LayerShell.KeyboardMode.NONE,
        )
        Gtk4LayerShell.set_anchor(self._window, Gtk4LayerShell.Edge.BOTTOM, True)
        Gtk4LayerShell.set_margin(self._window, Gtk4LayerShell.Edge.BOTTOM, _BOTTOM_MARGIN)
        Gtk4LayerShell.set_exclusive_zone(self._window, -1)

        # Transparent window background via CSS
        css = Gtk.CssProvider()
        css.load_from_string("window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Drawing area
        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        self._window.set_child(self._canvas)

        self._set_size(_CIRCLE_SIZE, _PILL_HEIGHT)

    # ── public thread-safe API ──────────────────────────────────────

    def show_recording(self) -> None:
        GLib.idle_add(self._do_show_recording)

    def update_audio_level(self, level: float) -> None:
        GLib.idle_add(self._do_update_level, level)

    def show_processing(self) -> None:
        GLib.idle_add(self._do_show_processing)

    def show_done(self) -> None:
        GLib.idle_add(self._do_show_done)

    def show_error(self) -> None:
        GLib.idle_add(self._do_show_error)

    def hide(self) -> None:
        GLib.idle_add(self._do_hide)

    # ── internal mode transitions (main thread only) ────────────────

    def _do_show_recording(self) -> None:
        self._cancel_timers()
        self._mode = _Mode.RECORDING
        self._levels.clear()
        self._levels.extend([0.0] * _NUM_BARS)
        self._set_size(_RECORDING_WIDTH, _PILL_HEIGHT)
        self._window.set_visible(True)
        self._canvas.queue_draw()

    def _do_update_level(self, level: float) -> None:
        if self._mode != _Mode.RECORDING:
            return
        self._levels.append(max(0.0, min(1.0, level)))
        self._canvas.queue_draw()

    def _do_show_processing(self) -> None:
        self._cancel_timers()
        self._mode = _Mode.PROCESSING
        self._spinner_angle = 0.0
        self._set_size(_CIRCLE_SIZE, _PILL_HEIGHT)
        self._window.set_visible(True)
        self._spinner_timer = GLib.timeout_add(_SPINNER_FPS_INTERVAL, self._tick_spinner)
        self._canvas.queue_draw()

    def _do_show_done(self) -> None:
        self._cancel_timers()
        self._mode = _Mode.DONE
        self._set_size(_CIRCLE_SIZE, _PILL_HEIGHT)
        self._window.set_visible(True)
        self._canvas.queue_draw()
        self._hide_timer = GLib.timeout_add(1000, self._do_hide_tick)

    def _do_show_error(self) -> None:
        self._cancel_timers()
        self._mode = _Mode.ERROR
        self._set_size(_CIRCLE_SIZE, _PILL_HEIGHT)
        self._window.set_visible(True)
        self._canvas.queue_draw()
        self._hide_timer = GLib.timeout_add(1500, self._do_hide_tick)

    def _do_hide(self) -> None:
        self._cancel_timers()
        self._mode = _Mode.HIDDEN
        self._window.set_visible(False)

    def _do_hide_tick(self) -> bool:
        """GLib.timeout callback — hides then returns False to stop timer."""
        self._hide_timer = None
        self._do_hide()
        return GLib.SOURCE_REMOVE

    # ── helpers ──────────────────────────────────────────────────────

    def _set_size(self, w: int, h: int) -> None:
        self._canvas.set_content_width(w)
        self._canvas.set_content_height(h)

    def _cancel_timers(self) -> None:
        if self._spinner_timer is not None:
            GLib.source_remove(self._spinner_timer)
            self._spinner_timer = None
        if self._hide_timer is not None:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None

    def _tick_spinner(self) -> bool:
        if self._mode != _Mode.PROCESSING:
            self._spinner_timer = None
            return GLib.SOURCE_REMOVE
        self._spinner_angle = (self._spinner_angle + 6) % 360
        self._canvas.queue_draw()
        return GLib.SOURCE_CONTINUE

    # ── drawing ─────────────────────────────────────────────────────

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, w: int, h: int) -> None:
        # Clear
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self._mode == _Mode.HIDDEN:
            return
        elif self._mode == _Mode.RECORDING:
            self._draw_recording(cr, w, h)
        elif self._mode == _Mode.PROCESSING:
            self._draw_processing(cr, w, h)
        elif self._mode == _Mode.DONE:
            self._draw_done(cr, w, h)
        elif self._mode == _Mode.ERROR:
            self._draw_error(cr, w, h)

    def _pill_path(self, cr: cairo.Context, w: int, h: int, inset: float = 0) -> None:
        """Trace a rounded-rectangle (pill) path, optionally inset for stroking."""
        r = h / 2 - inset
        cr.new_sub_path()
        cr.arc(w - h / 2, h / 2, r, -math.pi / 2, math.pi / 2)
        cr.arc(h / 2, h / 2, r, math.pi / 2, 3 * math.pi / 2)
        cr.close_path()

    def _draw_pill(self, cr: cairo.Context, w: int, h: int) -> None:
        """Draw a rounded-rectangle (pill) background with border."""
        self._pill_path(cr, w, h)
        cr.set_source_rgba(*_BG)
        cr.fill()
        self._pill_path(cr, w, h, inset=0.75)
        cr.set_source_rgb(*_WHITE)
        cr.set_line_width(1.5)
        cr.stroke()

    def _draw_circle_bg(self, cr: cairo.Context, w: int, h: int) -> None:
        """Draw a circular background with border centered in the canvas."""
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*_BG)
        cr.fill()
        cr.arc(cx, cy, r - 0.75, 0, 2 * math.pi)
        cr.set_source_rgb(*_WHITE)
        cr.set_line_width(1.5)
        cr.stroke()

    def _draw_recording(self, cr: cairo.Context, w: int, h: int) -> None:
        self._draw_pill(cr, w, h)

        total_bars_w = _NUM_BARS * _BAR_WIDTH + (_NUM_BARS - 1) * _BAR_GAP
        x_start = (w - total_bars_w) / 2
        cy = h / 2

        cr.set_source_rgb(*_WHITE)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(_BAR_WIDTH)

        for i, level in enumerate(self._levels):
            bar_h = _BAR_MIN_H + level * (_BAR_MAX_H - _BAR_MIN_H)
            x = x_start + i * (_BAR_WIDTH + _BAR_GAP) + _BAR_WIDTH / 2
            half = bar_h / 2
            cr.move_to(x, cy - half)
            cr.line_to(x, cy + half)
            cr.stroke()

    def _draw_processing(self, cr: cairo.Context, w: int, h: int) -> None:
        self._draw_circle_bg(cr, w, h)

        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 10

        cr.set_source_rgb(*_WHITE)
        cr.set_line_width(3)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        start = math.radians(self._spinner_angle)
        sweep = math.radians(270)
        cr.arc(cx, cy, r, start, start + sweep)
        cr.stroke()

    def _draw_done(self, cr: cairo.Context, w: int, h: int) -> None:
        self._draw_circle_bg(cr, w, h)

        cx, cy = w / 2, h / 2
        s = min(w, h) * 0.22  # scale factor

        cr.set_source_rgb(*_GREEN)
        cr.set_line_width(3.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

        cr.move_to(cx - s, cy)
        cr.line_to(cx - s * 0.25, cy + s * 0.7)
        cr.line_to(cx + s, cy - s * 0.6)
        cr.stroke()

    def _draw_error(self, cr: cairo.Context, w: int, h: int) -> None:
        self._draw_circle_bg(cr, w, h)

        cx, cy = w / 2, h / 2
        s = min(w, h) * 0.18

        cr.set_source_rgb(*_RED)
        cr.set_line_width(3.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        cr.move_to(cx - s, cy - s)
        cr.line_to(cx + s, cy + s)
        cr.stroke()
        cr.move_to(cx + s, cy - s)
        cr.line_to(cx - s, cy + s)
        cr.stroke()
