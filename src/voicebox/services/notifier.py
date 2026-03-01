"""Desktop notifications via notify-send."""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

APP_NAME = "Voicebox"
# This hint makes notifications replace each other instead of stacking
REPLACE_HINT = "string:x-canonical-private-synchronous:voicebox-status"


def notify(summary: str, body: str = "", urgency: str = "normal") -> None:
    """Send a desktop notification that replaces previous voicebox notifications."""
    try:
        cmd = [
            "notify-send",
            "--app-name", APP_NAME,
            "--hint", REPLACE_HINT,
            "--urgency", urgency,
            summary,
        ]
        if body:
            cmd.append(body)
        subprocess.run(cmd, check=True, timeout=5)
    except FileNotFoundError:
        log.debug("notify-send not found")
    except subprocess.SubprocessError as e:
        log.debug("Notification failed: %s", e)
