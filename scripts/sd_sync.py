"""Host CLI driving SD-sync ``list``/``pull``/``push`` over the device's data channel.

Usage
-----
    # List everything under the SD card root (or a subtree):
    python -m scripts.sd_sync list [SD_SUBPATH]

    # Pull a file from the SD card to the host:
    python -m scripts.sd_sync pull SD_PATH HOST_PATH

    # Push a host file to the SD card:
    python -m scripts.sd_sync push HOST_PATH SD_PATH

Every verb accepts ``--port`` to bypass auto-detection of the data-channel
serial port (see ``scripts.sd_sync_transport.find_data_port``). This CLI
talks to the device over serial only -- it never mounts or scans a CIRCUITPY
volume, so it works whether or not the host has one mounted at all.
"""

import argparse
import sys
from typing import IO

from hardware.shared.sd_sync_protocol import Transport
from scripts.sd_sync_client import SdSyncClient, SdSyncError
from scripts.sd_sync_transport import SdSyncPortError, find_data_port, open_serial_transport

__all__ = ["build_client", "dispatch", "main", "parse_args"]


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    """Parse CLI arguments into a namespace with a ``command`` plus its own paths."""
    parser = argparse.ArgumentParser(
        description="Drive SD-sync list/pull/push over a device's USB-CDC data channel."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Enumerate files on the SD card.")
    list_parser.add_argument(
        "sd_subpath",
        nargs="?",
        default="",
        help="Mount-relative subtree to list (default: the whole card root).",
    )

    pull_parser = subparsers.add_parser("pull", help="Download a file from the SD card.")
    pull_parser.add_argument("sd_path", help="Source path on the SD card.")
    pull_parser.add_argument("host_path", help="Destination path on the host.")

    push_parser = subparsers.add_parser("push", help="Upload a file to the SD card.")
    push_parser.add_argument("host_path", help="Source path on the host.")
    push_parser.add_argument("sd_path", help="Destination path on the SD card.")

    for sub in (list_parser, pull_parser, push_parser):
        sub.add_argument(
            "--port",
            default=None,
            help="Data-channel serial port (default: auto-detect via data_comports()).",
        )

    return parser.parse_args(argv)


def dispatch(args: argparse.Namespace, client: SdSyncClient, *, out: "IO[str]" = sys.stdout) -> int:
    """Run *args*'s command against *client*, printing results to *out*; return the exit code.

    Pure wiring: does not touch a transport itself, so it can be exercised
    against any ``SdSyncClient`` -- including one driven by a fake in-memory
    transport in tests, with no real device involved.
    """
    if args.command == "list":
        for path, size in client.list_files(args.sd_subpath):
            print(f"{path}\t{size}", file=out)
    elif args.command == "pull":
        client.pull(args.sd_path, args.host_path)
    elif args.command == "push":
        client.push(args.host_path, args.sd_path)
    return 0


def build_client(transport: Transport) -> SdSyncClient:
    """Construct the ``SdSyncClient`` this CLI drives over *transport*."""
    return SdSyncClient(transport)


def main(argv: "list[str] | None" = None) -> None:
    args = parse_args(argv)

    try:
        port = find_data_port(explicit_port=args.port)
    except SdSyncPortError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    transport = open_serial_transport(port)
    client = build_client(transport)

    try:
        exit_code = dispatch(args, client)
    except SdSyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
