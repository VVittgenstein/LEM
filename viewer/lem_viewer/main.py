"""CLI entry point for the terrain viewer."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lem-viewer",
        description="Interactive multi-channel terrain viewer for LEM-Diffusion",
    )
    parser.add_argument(
        "sources",
        nargs="*",
        help="File or directory paths to load (e.g. output/elevation.npy or output/)",
    )
    args = parser.parse_args(argv)

    from lem_viewer.app import Application

    app = Application(sources=args.sources or None)
    app.run()


if __name__ == "__main__":
    main()
