"""Tunnel sortant : l'application ouvre elle-meme la porte vers Internet.

Sans cela, la boutique devait lancer une commande dans un terminal, relever une
adresse et la recopier dans les reglages. Un gerant de magasin photo n'a pas a
faire ca : ici l'application demarre l'outil, lit l'adresse dans sa sortie et
l'utilise. Un interrupteur, rien d'autre.

L'outil est `cloudflared`, livre a cote de l'application (dossier `outils/`).
Il n'ouvre aucun port sur la box : c'est *lui* qui sort vers Cloudflare, et le
trafic revient par cette connexion deja etablie.

Deux formes de tunnel, la seconde n'attend que le serveur d'abonnement :

  - *rapide* — aucun compte, adresse tiree au hasard a chaque ouverture. Cela
    suffit parce que le QR code est fabrique a chaque depot : la boutique ne
    voit jamais l'adresse, donc peu importe qu'elle change.
  - *nomme* — un jeton et un sous-domaine stables, delivres avec la licence.
    `demarrer()` les accepte deja ; il ne manque que le serveur qui les emet.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

# Etapes montrees a l'utilisateur, dans l'ordre ou il les rencontre.
ARRETE = "arrete"
OUTIL_ABSENT = "outil_absent"
DEMARRAGE = "demarrage"
ACTIF = "actif"
ERREUR = "erreur"

MESSAGES = {
    ARRETE: "Dépôt à distance désactivé.",
    OUTIL_ABSENT: "L'outil de connexion est absent de cette installation.",
    DEMARRAGE: "Ouverture de la connexion…",
    ACTIF: "Dépôt à distance actif.",
    ERREUR: "La connexion n'a pas pu s'ouvrir.",
}

_ADRESSE = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")

# Au-dela, on cesse de relancer : l'outil echoue pour une raison qui ne se
# reglera pas toute seule (pas de reseau, sortie filtree, binaire casse).
_ESSAIS_MAX = 5
_ATTENTE_RELANCE = 5.0


def chemin_outil() -> str | None:
    """Ou trouver `cloudflared`, ou None s'il n'est pas la.

    Le dossier `outils/` livre avec l'application vient en premier : c'est la
    version que nous avons testee. Le PATH ensuite, pour un poste ou un
    administrateur l'a deja installe.
    """
    nom = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    livre = config.BASE_DIR / "outils" / nom
    if livre.is_file() and os.access(livre, os.X_OK if os.name != "nt" else os.F_OK):
        return str(livre)

    trouve = shutil.which("cloudflared")
    if trouve:
        return trouve

    for candidat in (
        Path("/usr/local/bin/cloudflared"),
        Path("/opt/homebrew/bin/cloudflared"),
        Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
        Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
    ):
        if candidat.is_file():
            return str(candidat)
    return None


def _sans_fenetre() -> dict:
    """Empeche Windows d'ouvrir une console noire devant le client."""
    if os.name != "nt":
        return {}
    infos = subprocess.STARTUPINFO()
    infos.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": infos, "creationflags": subprocess.CREATE_NO_WINDOW}


class Tunnel:
    """Le processus `cloudflared` et son etat, vus par le reste de l'application.

    Tout passe par un verrou : la page des reglages, le fil qui lit la sortie de
    l'outil et le fil qui le relance touchent aux memes champs.
    """

    def __init__(self) -> None:
        self._verrou = threading.RLock()
        self._processus: subprocess.Popen | None = None
        self._voulu = False          # la boutique a-t-elle demande le tunnel ?
        self._etape = ARRETE
        self._url = ""
        self._detail = ""            # derniere ligne d'erreur utile, pour le support
        self._essais = 0
        self._port = 0
        self._jeton = ""
        self._observateurs: list = []

    # --- lecture ----------------------------------------------------------

    def url(self) -> str:
        """L'adresse publique si le tunnel est ouvert, sinon une chaine vide."""
        with self._verrou:
            return self._url if self._etape == ACTIF else ""

    def etat(self) -> dict:
        with self._verrou:
            return {
                "etape": self._etape,
                "message": MESSAGES.get(self._etape, ""),
                "detail": self._detail,
                "url": self._url if self._etape == ACTIF else "",
                "outil": chemin_outil() is not None,
                "actif": self._etape == ACTIF,
            }

    def observer(self, rappel) -> None:
        """S'abonner aux changements d'etat, pour les pousser aux pages ouvertes."""
        with self._verrou:
            self._observateurs.append(rappel)

    def _annoncer(self) -> None:
        etat = self.etat()
        with self._verrou:
            rappels = list(self._observateurs)
        for rappel in rappels:
            try:
                rappel(etat)
            except Exception:  # pragma: no cover - un abonne ne casse pas le tunnel
                pass

    def _poser(self, etape: str, url: str | None = None, detail: str | None = None) -> None:
        with self._verrou:
            change = etape != self._etape or (url is not None and url != self._url)
            self._etape = etape
            if url is not None:
                self._url = url
            if detail is not None:
                self._detail = detail
        if change:
            self._annoncer()

    # --- conduite ---------------------------------------------------------

    def demarrer(self, port: int, jeton: str = "") -> dict:
        """Ouvre le tunnel vers la porte publique. Sans effet s'il tourne deja.

        `jeton` est celui d'un tunnel nomme, delivre avec l'abonnement. Vide,
        on ouvre un tunnel rapide, dont l'adresse est tiree au hasard.
        """
        with self._verrou:
            self._voulu = True
            self._port = port
            self._jeton = jeton
            self._essais = 0
            if self._processus is not None and self._processus.poll() is None:
                return self.etat()
        self._lancer()
        return self.etat()

    def arreter(self) -> dict:
        with self._verrou:
            self._voulu = False
            processus = self._processus
            self._processus = None
        self._tuer(processus)
        self._poser(ARRETE, url="", detail="")
        return self.etat()

    @staticmethod
    def _tuer(processus: subprocess.Popen | None) -> None:
        if processus is None or processus.poll() is not None:
            return
        processus.terminate()
        try:
            processus.wait(timeout=5)
        except subprocess.TimeoutExpired:
            processus.kill()

    def _lancer(self) -> None:
        outil = chemin_outil()
        if outil is None:
            self._poser(OUTIL_ABSENT, url="")
            return

        with self._verrou:
            port, jeton = self._port, self._jeton

        commande = [outil, "tunnel", "--no-autoupdate"]
        if jeton:
            commande += ["run", "--token", jeton]
        else:
            commande += ["--url", f"http://{config.PUBLIC_HOST}:{port}"]

        self._poser(DEMARRAGE, url="", detail="")
        try:
            processus = subprocess.Popen(
                commande,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                errors="replace",
                **_sans_fenetre(),
            )
        except OSError as exc:
            return self._poser(ERREUR, url="", detail=str(exc))

        with self._verrou:
            self._processus = processus
        threading.Thread(target=self._lire, args=(processus,), daemon=True).start()

    def _lire(self, processus: subprocess.Popen) -> None:
        """Suit la sortie de l'outil : c'est la qu'il annonce son adresse."""
        derniere_erreur = ""
        for ligne in processus.stdout or ():
            trouvee = _ADRESSE.search(ligne)
            if trouvee:
                self._poser(ACTIF, url=trouvee.group(0), detail="")
            elif "ERR" in ligne or "error" in ligne.lower():
                derniere_erreur = ligne.strip()[-300:]

        processus.wait()
        with self._verrou:
            fini = self._processus is processus
            voulu = self._voulu
            if fini:
                self._processus = None
        if not fini or not voulu:
            return  # arret demande, ou remplace par un lancement plus recent

        self._relancer(derniere_erreur)

    def _relancer(self, derniere_erreur: str) -> None:
        """L'outil s'est arrete tout seul : on reessaie, un nombre borne de fois."""
        with self._verrou:
            self._essais += 1
            trop = self._essais > _ESSAIS_MAX
        if trop:
            return self._poser(
                ERREUR, url="",
                detail=derniere_erreur or "La connexion s'interrompt sans cesse.",
            )
        self._poser(DEMARRAGE, url="", detail=derniere_erreur)
        time.sleep(_ATTENTE_RELANCE)
        with self._verrou:
            if not self._voulu:
                return
        self._lancer()


TUNNEL = Tunnel()
