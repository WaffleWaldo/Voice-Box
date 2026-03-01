"""Window context via niri IPC (Unix socket)."""

from __future__ import annotations

import json
import logging
import os
import socket

log = logging.getLogger(__name__)


def get_focused_window() -> dict[str, str]:
    """Query niri for the focused window's app_id and title.

    Returns dict with 'app_id' and 'title' keys, empty strings on failure.
    """
    result = {"app_id": "", "title": ""}
    sock_path = os.environ.get("NIRI_SOCKET", "")
    if not sock_path:
        log.debug("NIRI_SOCKET not set")
        return result

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(sock_path)
            sock.sendall(b'"FocusedWindow"\n')

            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                # niri sends a single JSON response then we can break
                try:
                    json.loads(data)
                    break
                except json.JSONDecodeError:
                    continue

            response = json.loads(data)
            # niri response: {"Ok": {"FocusedWindow": {"id": ..., "app_id": "...", "title": "..."}}}
            if "Ok" in response:
                window = response["Ok"]
                if "FocusedWindow" in window:
                    win = window["FocusedWindow"]
                    if win is not None:
                        result["app_id"] = win.get("app_id", "")
                        result["title"] = win.get("title", "")
                        log.debug("Focused window: %s — %s", result["app_id"], result["title"])
    except (OSError, json.JSONDecodeError, KeyError) as e:
        log.debug("niri IPC failed: %s", e)

    return result
