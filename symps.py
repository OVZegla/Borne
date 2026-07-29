#!/usr/bin/env python3
"""Point d'entree du Symp's Kiosk.

Au lancement, l'application cherche une machine du meme atelier deja demarree
sur le reseau local :

  - elle en trouve une  -> ce poste s'y connecte, rien a configurer ;
  - elle n'en trouve pas -> cette machine devient l'hote et stocke les depots.

Usage :
    python3 symps.py [--port 8080] [--hote] [--poste] [--no-browser]
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

if sys.version_info < (3, 8):  # pragma: no cover
    sys.exit("Python 3.8 ou superieur est requis (detecte : %s)" % sys.version.split()[0])

from kiosk import config, reseau, server


def main() -> None:
    parser = argparse.ArgumentParser(description="Symp's Kiosk — borne de depot de photos")
    parser.add_argument("--port", type=int, default=config.PORT, help="port d'ecoute")
    parser.add_argument("--host", default=config.HOST, help="interface d'ecoute")
    parser.add_argument(
        "--hote", action="store_true",
        help="forcer cette machine comme hote, sans chercher sur le reseau",
    )
    parser.add_argument(
        "--poste", action="store_true",
        help="se connecter uniquement a un hote existant, sans en devenir un",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="ne pas ouvrir le navigateur au demarrage"
    )
    args = parser.parse_args()

    if args.hote and args.poste:
        parser.error("--hote et --poste s'excluent")

    atelier = config.atelier()

    if not args.hote:
        hotes = reseau.chercher_hotes(atelier)
        if hotes:
            return rejoindre(hotes[0], ouvrir=not args.no_browser)
        if args.poste:
            sys.exit(
                "\n  Aucune machine Symp's Kiosk trouvee sur ce reseau.\n"
                "  Verifiez que l'hote est allume et sur le meme Wi-Fi,\n"
                "  ou lancez-le ici avec : ./start.sh --hote\n"
            )

    server.serve(
        args.host, args.port, open_browser=not args.no_browser, atelier=atelier
    )


def rejoindre(hote: dict, ouvrir: bool) -> None:
    """Ce poste se raccroche a l'hote deja en service."""
    print(f"\n  {config.BRAND_NAME} — poste connecte.\n")
    print(f"  Hote trouve : {hote.get('nom') or hote['host']}")
    print(f"  Adresse     : {hote['url']}\n")
    print("  Cette fenetre peut rester ouverte ou etre fermee.\n")
    if ouvrir:
        webbrowser.open(hote["url"])


if __name__ == "__main__":
    main()
