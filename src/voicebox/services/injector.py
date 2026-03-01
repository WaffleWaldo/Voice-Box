"""Text injection via wtype (with wl-clipboard fallback for long text)."""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voicebox.config import InjectorConfig

log = logging.getLogger(__name__)


class Injector:
    """Injects text into the focused Wayland window."""

    def __init__(self, config: InjectorConfig) -> None:
        self._delay_ms = config.type_delay_ms
        self._clipboard_threshold = config.clipboard_threshold

    def inject(self, text: str) -> bool:
        """Inject text into focused window. Returns True on success."""
        if not text:
            return False

        if len(text) > self._clipboard_threshold:
            return self._inject_clipboard(text)
        return self._inject_type(text)

    def _inject_type(self, text: str) -> bool:
        """Type text directly via wtype."""
        try:
            cmd = ["wtype", "--"]
            if self._delay_ms > 0:
                cmd = ["wtype", "-d", str(self._delay_ms), "--"]
            cmd.append(text)
            subprocess.run(cmd, check=True, timeout=10)
            log.info("Injected %d chars via wtype", len(text))
            return True
        except FileNotFoundError:
            log.error("wtype not found — install with: pacman -S wtype")
            return False
        except subprocess.SubprocessError as e:
            log.error("wtype failed: %s", e)
            return False

    def _inject_clipboard(self, text: str) -> bool:
        """Copy to clipboard, then paste via wtype Ctrl+V."""
        try:
            # Save current clipboard
            old_clip = None
            try:
                result = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, text=True, timeout=2,
                )
                if result.returncode == 0:
                    old_clip = result.stdout
            except subprocess.SubprocessError:
                pass

            # Copy new text
            subprocess.run(
                ["wl-copy", "--"],
                input=text, text=True, check=True, timeout=5,
            )

            # Paste
            subprocess.run(
                ["wtype", "-M", "ctrl", "v", "-m", "ctrl"],
                check=True, timeout=10,
            )
            log.info("Injected %d chars via clipboard paste", len(text))

            # Restore old clipboard
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
