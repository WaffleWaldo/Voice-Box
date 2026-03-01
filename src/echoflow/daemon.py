"""Unix socket daemon server with GTK4 main loop."""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from echoflow.config import Config

log = logging.getLogger(__name__)

SOCKET_PATH = f"/run/user/{os.getuid()}/echoflow.sock"


def _get_socket_path() -> str:
    return SOCKET_PATH


def _glib():
    from gi.repository import GLib
    return GLib


class Daemon:
    """GTK4 application daemon with GLib-integrated Unix socket."""

    def __init__(self, config: Config | None = None) -> None:
        from echoflow.config import load_config

        self._config = config or load_config()
        self._pipeline = None
        self._overlay = None
        self._server: socket.socket | None = None
        self._fd_source: int | None = None
        self._app = None

    def run(self) -> None:
        """Start the daemon. Blocks until shutdown."""
        import ctypes
        # Must load gtk4-layer-shell BEFORE libwayland-client (pulled in by GTK)
        # so layer surfaces initialize correctly and the overlay never steals focus.
        ctypes.CDLL("libgtk4-layer-shell.so", mode=ctypes.RTLD_GLOBAL)

        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gio

        app = Gtk.Application(
            application_id="dev.echoflow.daemon",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self._app = app
        app.connect("activate", self._on_activate)
        app.run(None)

    def _on_activate(self, app) -> None:
        """Called once on the main thread when GTK is ready."""
        from echoflow.core.pipeline import Pipeline
        from echoflow.services.overlay import Overlay

        GLib = _glib()
        sock_path = _get_socket_path()

        # Clean up stale socket
        if os.path.exists(sock_path):
            os.unlink(sock_path)

        # Create overlay (if enabled) and pipeline
        if self._config.overlay.enabled:
            self._overlay = Overlay(app)
        self._pipeline = Pipeline(self._config, overlay=self._overlay)

        # Non-blocking Unix socket integrated with GLib
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(sock_path)
        self._server.listen(5)
        self._server.setblocking(False)

        self._fd_source = GLib.unix_fd_add_full(
            GLib.PRIORITY_DEFAULT,
            self._server.fileno(),
            GLib.IOCondition.IN,
            self._on_socket_ready,
        )

        # Signal handling via GLib
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_signal)

        log.info("Daemon listening on %s", sock_path)

    def _on_socket_ready(self, fd: int, condition: int) -> bool:
        """GLib callback when a client connects to the Unix socket."""
        GLib = _glib()
        try:
            conn, _ = self._server.accept()
            thread = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            thread.start()
        except BlockingIOError:
            pass
        except OSError:
            log.exception("Socket accept error")
        return GLib.SOURCE_CONTINUE

    def _handle(self, conn: socket.socket) -> None:
        """Handle a single client connection (runs in a worker thread)."""
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                return

            response = self._dispatch(data)
            conn.sendall(response.encode())
        except Exception:
            log.exception("Error handling command")
            try:
                conn.sendall(b"error")
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, command: str) -> str:
        """Dispatch a command and return the response string."""
        assert self._pipeline is not None

        if command == "toggle":
            result = self._pipeline.toggle()
            log.info("Toggle → %s", result)
            return result
        elif command == "status":
            return self._pipeline.state.value
        elif command == "quit":
            log.info("Quit command received")
            self._quit()
            return "stopping"
        else:
            return f"unknown command: {command}"

    def _on_signal(self) -> bool:
        GLib = _glib()
        log.info("Signal received, shutting down")
        self._quit()
        return GLib.SOURCE_REMOVE

    def _quit(self) -> None:
        """Initiate clean shutdown from any thread."""
        GLib = _glib()
        GLib.idle_add(self._do_quit)

    def _do_quit(self) -> None:
        """Runs on the main thread to clean up and quit."""
        GLib = _glib()
        sock_path = _get_socket_path()

        if self._fd_source is not None:
            GLib.source_remove(self._fd_source)
            self._fd_source = None
        if self._pipeline:
            self._pipeline.shutdown()
        if self._server:
            self._server.close()
            self._server = None
        if os.path.exists(sock_path):
            os.unlink(sock_path)

        log.info("Daemon stopped")
        self._app.quit()


def send_command(command: str) -> str:
    """Send a command to the running daemon and return the response."""
    sock_path = _get_socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(sock_path)
            sock.sendall(command.encode())
            return sock.recv(1024).decode()
    except FileNotFoundError:
        return "error: daemon not running (socket not found)"
    except ConnectionRefusedError:
        return "error: daemon not running (connection refused)"
    except socket.timeout:
        return "error: daemon not responding"
