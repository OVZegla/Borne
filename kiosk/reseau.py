"""Decouverte automatique des machines du meme atelier sur le reseau local.

Une machine tient le role d'hote : elle stocke les depots et fait tourner le
serveur. Les autres (borne, poste de reception) n'ont rien a configurer, elles
la trouvent toutes seules.

Le dialogue tient en deux messages UDP diffuses sur le reseau local :

    poste  -->  diffusion   SYMPS?1 <atelier>
    hote   -->  reponse     SYMPS!1 {"host": "...", "port": 8080, ...}

L'identifiant d'atelier evite qu'une borne rejoigne l'hote de la boutique
voisine sur un reseau partage. Ce n'est pas un secret : c'est le compte
abonne qui authentifiera reellement les machines.
"""

from __future__ import annotations

import json
import socket
import threading
import time

from . import config

PROTOCOLE = 1
PORT_DECOUVERTE = config.DISCOVERY_PORT
_PREFIXE_QUESTION = f"SYMPS?{PROTOCOLE} ".encode()
_PREFIXE_REPONSE = f"SYMPS!{PROTOCOLE} ".encode()

# Au-dela, on considere que le paquet n'est pas des notres.
_TAILLE_MAX = 2048


def _adresse_locale() -> str:
    """Adresse IPv4 de cette machine sur le reseau local."""
    sonde = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sonde.connect(("192.168.255.255", 1))
        return sonde.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sonde.close()


class Annonceur:
    """Repond aux recherches des autres machines de l'atelier."""

    def __init__(self, atelier: str, port_service: int, nom: str | None = None) -> None:
        self.atelier = atelier
        self.port_service = port_service
        self.nom = nom or socket.gethostname()
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None

    def demarrer(self) -> None:
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()

    def _carte_de_visite(self) -> bytes:
        fiche = {
            "atelier": self.atelier,
            "host": _adresse_locale(),
            "port": self.port_service,
            "nom": self.nom,
            "version": config.VERSION,
        }
        return _PREFIXE_REPONSE + json.dumps(fiche, ensure_ascii=False).encode("utf-8")

    def _boucle(self) -> None:
        prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prise.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            prise.bind(("", PORT_DECOUVERTE))
        except OSError:
            # Un autre hote ecoute deja sur ce port : on ne double pas l'annonce.
            prise.close()
            return

        prise.settimeout(0.5)
        try:
            while not self._arret.is_set():
                try:
                    paquet, origine = prise.recvfrom(_TAILLE_MAX)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not paquet.startswith(_PREFIXE_QUESTION):
                    continue
                demande = paquet[len(_PREFIXE_QUESTION):].decode("utf-8", "replace").strip()
                # Une recherche sans atelier precise interroge tout le monde.
                if demande and demande != self.atelier:
                    continue
                try:
                    prise.sendto(self._carte_de_visite(), origine)
                except OSError:
                    continue
        finally:
            prise.close()


def chercher_hotes(atelier: str = "", duree: float = 1.5) -> list[dict]:
    """Diffuse une recherche et retourne les hotes qui repondent."""
    prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    prise.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    prise.settimeout(0.3)

    question = _PREFIXE_QUESTION + atelier.encode("utf-8")
    for cible in ("255.255.255.255", "127.0.0.1"):
        try:
            prise.sendto(question, (cible, PORT_DECOUVERTE))
        except OSError:
            continue

    trouves: dict[tuple[str, int], dict] = {}
    fin = time.monotonic() + duree
    try:
        while time.monotonic() < fin:
            try:
                paquet, origine = prise.recvfrom(_TAILLE_MAX)
            except socket.timeout:
                continue
            except OSError:
                break

            if not paquet.startswith(_PREFIXE_REPONSE):
                continue
            try:
                fiche = json.loads(paquet[len(_PREFIXE_REPONSE):].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(fiche, dict) or "port" not in fiche:
                continue
            if atelier and fiche.get("atelier") != atelier:
                continue

            # L'adresse vue par le reseau prime sur celle que l'hote declare :
            # elle est juste meme si la machine a plusieurs interfaces.
            fiche["host"] = origine[0]
            fiche["url"] = f"http://{origine[0]}:{fiche['port']}"
            trouves[(origine[0], fiche["port"])] = fiche
    finally:
        prise.close()

    return sorted(trouves.values(), key=lambda f: (f.get("nom") or "", f["host"]))
