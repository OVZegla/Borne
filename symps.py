#!/usr/bin/env python3
"""Point d'entree du Symp's Kiosk.

Usage :
    python3 symps.py [--port 8080] [--host 0.0.0.0] [--no-browser]
"""

from __future__ import annotations

import argparse
import sys

if sys.version_info < (3, 8):  # pragma: no cover
    sys.exit("Python 3.8 ou superieur est requis (detecte : %s)" % sys.version.split()[0])

from kiosk import config, server


def main() -> None:
    parser = argparse.ArgumentParser(description="Symp's Kiosk — borne de depot d'images")
    parser.add_argument("--port", type=int, default=config.PORT, help="port d'ecoute")
    parser.add_argument("--host", default=config.HOST, help="interface d'ecoute")
    parser.add_argument(
        "--no-browser", action="store_true", help="ne pas ouvrir le navigateur au demarrage"
    )
    args = parser.parse_args()

    server.serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
