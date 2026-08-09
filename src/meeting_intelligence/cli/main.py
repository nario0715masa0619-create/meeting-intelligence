"""Phase 1 command-line skeleton."""

import argparse
from collections.abc import Sequence
from meeting_intelligence import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting-process", description="Process a meeting recording into canonical records.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_usage()
    print("processing pipeline is not implemented in Phase 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
