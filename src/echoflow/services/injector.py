"""Text injection via clipboard paste (wl-copy + ydotool/wtype Ctrl+V)."""

from __future__ import annotations

import logging
import subprocess
import time

log = logging.getLogger(__name__)

# Terminal emulators that use Ctrl+Shift+V instead of Ctrl+V
TERMINAL_APP_IDS = frozenset({
    "foot",
    "footclient",
    "ghostty",
    "Alacritty",
    "kitty",
    "org.wezfurlong.wezterm",
    "com.mitchellh.ghostty",
    "org.gnome.Terminal",
    "org.kde.konsole",
    "xterm",
    "urxvt",
})


class Injector:
    """Injects text into the focused Wayland window via clipboard paste."""

    def inject(self, text: str, app_id: str = "") -> bool:
        """Inject text into focused window. Returns True on success."""
        if not text:
            return False

        try:
            # Save current clipboard
            old_clip = None
            try:
                result = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, timeout=2,
                )
                if result.returncode == 0:
                    old_clip = result.stdout.decode("utf-8")
            except (subprocess.SubprocessError, UnicodeDecodeError):
                pass

            # Copy text to clipboard
            subprocess.run(
                ["wl-copy", "--"],
                input=text, text=True, check=True, timeout=5,
            )

            # Paste — terminals use wtype Ctrl+Shift+V, everything else
            # uses ydotool Ctrl+V (wtype's virtual-keyboard protocol
            # doesn't work with Chrome/Electron apps).
            if app_id in TERMINAL_APP_IDS:
                subprocess.run(
                    ["wtype", "-M", "ctrl", "-M", "shift", "v", "-m", "shift", "-m", "ctrl"],
                    check=True, timeout=10,
                )
                log.info("Injected %d chars via wtype Ctrl+Shift+V (terminal: %s)", len(text), app_id)
            else:
                # ydotool key codes: 29=Left Ctrl, 47=V
                subprocess.run(
                    ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
                    check=True, timeout=10,
                )
                log.info("Injected %d chars via ydotool Ctrl+V (app: %s)", len(text), app_id)

            # Delay before restoring clipboard — apps read it
            # asynchronously after the Ctrl+V keystroke lands.
            time.sleep(0.1)

            # Restore previous clipboard
            if old_clip is not None:
                subprocess.run(
                    ["wl-copy", "--"],
                    input=old_clip, text=True, timeout=2,
                )

            return True
        except FileNotFoundError as e:
            log.error("Missing tool: %s", e)
            return False
        except subprocess.SubprocessError as e:
            log.error("Clipboard injection failed: %s", e)
            return False
