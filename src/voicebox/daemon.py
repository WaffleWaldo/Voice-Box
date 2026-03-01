"""Unix socket daemon server."""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading

from voicebox.config import Config, load_config
from voicebox.core.pipeline import Pipeline

log = logging.getLogger(__name__)

SOCKET_PATH = f"/run/user/{os.getuid()}/voicebox.sock"


def _get_socket_path() -> str:
    return SOCKET_PATH


class Daemon:
    """Listens on a Unix socket for toggle/status/quit commands."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or load_config()
        self._pipeline: Pipeline | None = None
        self._server: socket.socket | None = None
        self._running = False

    def run(self) -> None:
        """Start the daemon. Blocks until shutdown."""
        sock_path = _get_socket_path()

        # Clean up stale socket
        if os.path.exists(sock_path):
            os.unlink(sock_path)

        self._pipeline = Pipeline(self._config)

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(sock_path)
        self._server.listen(5)
        self._server.settimeout(1.0)  # Allow periodic shutdown checks
        self._running = True

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        log.info("Daemon listening on %s", sock_path)

        while self._running:
            try:
                conn, _ = self._server.accept()
                thread = threading.Thread(target=self._handle, args=(conn,), daemon=True)
                thread.start()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    log.exception("Socket error")
                break

        self._shutdown(sock_path)

    def _handle(self, conn: socket.socket) -> None:
        """Handle a single client connection."""
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
            self._running = False
            return "stopping"
        else:
            return f"unknown command: {command}"

    def _signal_handler(self, signum: int, frame: object) -> None:
        log.info("Signal %d received, shutting down", signum)
        self._running = False

    def _shutdown(self, sock_path: str) -> None:
        if self._pipeline:
            self._pipeline.shutdown()
        if self._server:
            self._server.close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        log.info("Daemon stopped")


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
