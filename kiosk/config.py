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

# --- porte publique ----------------------------------------------------------
# Le QR code de la borne encode une adresse. Tant que c'est celle du reseau
# local (192.168.x.y), seul un telephone pose sur le meme Wi-Fi peut deposer.
# Pour que le depot marche depuis n'importe quel reseau, la boutique ouvre un
# tunnel sortant (Cloudflare Tunnel, ngrok...) qui lui donne une adresse
# publique en https, et la declare dans ses reglages.
#
# Cette adresse ne doit surtout pas mener au serveur entier : la reception, le
# tableau de bord, les reglages et le choix du role se retrouveraient sur
# Internet. Le tunnel se branche donc sur une *seconde* porte, ouverte sur la
# boucle locale uniquement, qui ne sert que les pages du telephone du client.
PUBLIC_HOST = os.environ.get("SYMPS_PUBLIC_HOST", "127.0.0.1")

# Adresse publique imposee par l'environnement. Renseignee, elle l'emporte sur
# le reglage saisi dans la page d'administration.
PUBLIC_URL = os.environ.get("SYMPS_PUBLIC_URL", "").strip()


def port_public(port_principal: int, valeur: str | None = None) -> int:
    """Port de la porte publique, 0 si elle doit rester fermee.

    Par defaut le port principal + 1, calcule *apres* coup : le serveur glisse
    au port suivant quand le sien est pris, et les deux portes se marcheraient
    dessus si le calcul se faisait sur le port demande.
    """
    brut = (os.environ.get("SYMPS_PUBLIC_PORT", "") if valeur is None else valeur).strip().lower()
    if brut in ("off", "non", "aucun", "0"):
        return 0
    try:
        return int(brut)
    except ValueError:
        return port_principal + 1

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


def machine() -> str:
    """Identifiant stable de ce poste, pour compter les machines d'un abonnement."""
    impose = os.environ.get("SYMPS_MACHINE")
    if impose:
        return impose
    fichier = DATA_DIR / "machine.txt"
    try:
        existant = fichier.read_text("utf-8").strip()
        if existant:
            return existant
    except OSError:
        pass
    nouveau = secrets.token_hex(8)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fichier.write_text(nouveau, "utf-8")
    except OSError:
        pass
    return nouveau


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

# --- abonnement --------------------------------------------------------------
# Adresse du serveur de licences. Elle est vide sur une copie de developpement :
# l'application tourne alors sans abonnement. Les versions livrees aux clients
# sont construites avec cette valeur renseignee, ce qui active la connexion.
LICENCE_URL = os.environ.get("SYMPS_LICENCE_URL", "").strip()

# Cle *publique* du serveur de licences. Elle ne permet que de verifier une
# licence, jamais d'en fabriquer : elle peut donc etre livree avec l'application.
LICENCE_CLE_PUBLIQUE = os.environ.get("SYMPS_LICENCE_CLE", "").strip()

# Duree pendant laquelle l'application continue de fonctionner sans joindre le
# serveur. Une boutique privee d'Internet ne doit pas s'arreter de vendre.
LICENCE_GRACE_HEURES = _int_env("SYMPS_LICENCE_GRACE_HEURES", 72)


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
