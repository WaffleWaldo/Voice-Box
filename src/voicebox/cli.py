"""CLI entry point for voicebox."""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voicebox",
        description="Linux voice-to-text daemon",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("daemon", help="Start the voicebox daemon")
    sub.add_parser("toggle", help="Toggle recording on/off")
    sub.add_parser("status", help="Query daemon status")
    sub.add_parser("stop", help="Stop the daemon")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "daemon":
        _run_daemon()
    elif args.command in ("toggle", "status", "stop"):
        _send(args.command)
    else:
        parser.print_help()
        sys.exit(1)


def _run_daemon() -> None:
    from voicebox.config import load_config
    from voicebox.daemon import Daemon

    config = load_config()
    daemon = Daemon(config)
    daemon.run()


def _send(command: str) -> None:
    from voicebox.daemon import send_command

    if command == "stop":
        command = "quit"

    response = send_command(command)
    print(response)
