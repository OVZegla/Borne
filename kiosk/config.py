"""Configuration du Symp's Kiosk, surchargeable par variables d'environnement."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


HOST = os.environ.get("SYMPS_HOST", "0.0.0.0")
PORT = _int_env("SYMPS_PORT", 8080)

# Port UDP sur lequel les machines d'un meme atelier se cherchent.
DISCOVERY_PORT = _int_env("SYMPS_DISCOVERY_PORT", 8079)

def dossier_donnees_par_defaut(
    nom_os: str | None = None, plateforme: str | None = None, env: dict | None = None
) -> str:
    """Emplacement inscriptible propre a chaque systeme.

    L'application est souvent installee dans un dossier en lecture seule
    (« Program Files » sous Windows, « Applications » sous macOS) : les depots
    ne peuvent pas etre ecrits a cote du programme.

    Les parametres n'existent que pour rendre la fonction testable depuis un
    autre systeme ; en usage normal ils sont deduits de la machine.
    """
    nom_os = os.name if nom_os is None else nom_os
    plateforme = sys.platform if plateforme is None else plateforme
    env = os.environ if env is None else env
    maison = env.get("HOME") or env.get("USERPROFILE") or os.path.expanduser("~")

    if nom_os == "nt":
        return os.path.join(env.get("LOCALAPPDATA") or maison, "Symp's Kiosk", "depots")
    if plateforme == "darwin":
        return os.path.join(maison, "Library", "Application Support", "Symp's Kiosk", "depots")
    racine = env.get("XDG_DATA_HOME") or os.path.join(maison, ".local", "share")
    return os.path.join(racine, "symps-kiosk", "depots")


def port_reutilisable(nom_os: str | None = None) -> bool:
    """SO_REUSEADDR est-il sur a activer sur ce systeme ?

    Sous Windows il autorise deux processus a se lier au meme port : le repli
    sur le port suivant ne se declencherait pas et deux instances se
    partageraient les connexions. Ailleurs il signifie seulement « reutiliser un
    port encore en TIME_WAIT », ce que l'on veut.
    """
    return (os.name if nom_os is None else nom_os) != "nt"


DATA_DIR = Path(os.environ.get("SYMPS_DATA") or dossier_donnees_par_defaut()).resolve()
FILES_DIR = DATA_DIR / "fichiers"
INDEX_FILE = DATA_DIR / "index.json"

# Duree de vie d'un depot valide avant suppression automatique.
RETENTION_HOURS = _int_env("SYMPS_RETENTION_HOURS", 24)

# Duree au bout de laquelle une session restee vide (borne rafraichie, client
# parti sans envoyer) est oubliee.
DRAFT_RETENTION_HOURS = _int_env("SYMPS_DRAFT_HOURS", 2)

MAX_FILE_BYTES = _int_env("SYMPS_MAX_MB", 25) * 1024 * 1024
MAX_FILES_PER_TICKET = _int_env("SYMPS_MAX_FILES", 20)

CODE_LENGTH = 4

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "application/pdf": ".pdf",
}

BRAND_NAME = "Symp's Kiosk"
BRAND_COLOR = "#00287E"


def atelier() -> str:
    """Identifiant de l'atelier, partage par les machines d'une meme boutique.

    Genere localement au premier lancement. Il prendra la valeur de l'identifiant
    du compte abonne le jour ou l'activation par licence sera en place.
    """
    impose = os.environ.get("SYMPS_ATELIER")
    if impose:
        return impose

    fichier = DATA_DIR / "atelier.txt"
    try:
        existant = fichier.read_text("utf-8").strip()
        if existant:
            return existant
    except OSError:
        pass

    nouveau = secrets.token_hex(6)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fichier.write_text(nouveau, "utf-8")
    except OSError:
        pass
    return nouveau
