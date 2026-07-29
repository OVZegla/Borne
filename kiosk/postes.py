"""Role de chaque appareil : borne, imprimante ou PC.

L'abonnement se valide une seule fois, sur la machine qui heberge l'application.
Les autres appareils de la boutique arrivent par le reseau local et n'ont rien a
saisir : ils declarent simplement ce qu'ils sont, et ce choix est retenu.

Ce que chacun voit en decoule :

  - la *borne* ne montre que l'ecran face au client. Elle n'atteint ni la
    reception, ni les reglages : un client qui tapote l'ecran ne doit pas
    tomber sur les tarifs ou sur les depots des autres ;
  - l'*imprimante* est le poste de retrait : reception, impression, reglages ;
  - le *PC* ajoute le tableau de bord de la boutique.

Le role tient dans un jeton tire au hasard, pose en cookie et conserve ici. Un
appareil ne peut donc pas s'inventer un role en modifiant son cookie : il ne
connait pas les jetons des autres.
"""

from __future__ import annotations

import json
import secrets
import threading
import time

from . import config

BORNE = "borne"
IMPRIMANTE = "imprimante"
PC = "pc"

ROLES = {
    BORNE: {
        "nom": "Borne",
        "resume": "L'écran face au client : QR code, choix du tirage, code de retrait.",
        "accueil": "/",
    },
    IMPRIMANTE: {
        "nom": "Imprimante",
        "resume": "Le poste de retrait : dépôts, encaissement, impression, réglages.",
        "accueil": "/recuperer",
    },
    PC: {
        "nom": "PC",
        "resume": "Le poste de gestion : tableau de bord, dépôts, réglages.",
        "accueil": "/tableau",
    },
}

# Droits attaches a chaque role. Le serveur s'y fie pour toutes ses routes : la
# borne n'a pas seulement un menu allege, elle recoit un refus.
DROITS = {
    BORNE: frozenset({"borne"}),
    IMPRIMANTE: frozenset({"reception", "impression", "reglages"}),
    PC: frozenset({"reception", "impression", "reglages", "tableau"}),
}

COOKIE = "poste"

_verrou = threading.RLock()
_cache: dict | None = None


class PosteError(ValueError):
    """Role refuse."""


def _fichier():
    return config.DATA_DIR / "postes.json"


def _tous() -> dict:
    global _cache
    with _verrou:
        if _cache is None:
            try:
                lu = json.loads(_fichier().read_text("utf-8"))
                _cache = lu if isinstance(lu, dict) else {}
            except (OSError, json.JSONDecodeError):
                _cache = {}
        return _cache


def _ecrire() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _fichier().write_text(json.dumps(_tous(), ensure_ascii=False, indent=1), "utf-8")


def recharger() -> None:
    """Oublie le cache : utile en test."""
    global _cache
    with _verrou:
        _cache = None


def inscrire(role: str, nom: str = "") -> str:
    """Enregistre un appareil dans ce role et renvoie son jeton."""
    if role not in ROLES:
        raise PosteError("Role inconnu")
    jeton = secrets.token_urlsafe(18)
    with _verrou:
        _tous()[jeton] = {
            "role": role,
            "nom": str(nom or "").strip()[:40],
            "inscrit_le": time.time(),
            "vu_le": time.time(),
        }
        _ecrire()
    return jeton


def role_de(jeton: str | None) -> str | None:
    """Role d'un appareil, ou None si son jeton est inconnu."""
    if not jeton:
        return None
    entree = _tous().get(jeton)
    return entree["role"] if entree else None


def vu(jeton: str | None) -> None:
    """Note le passage d'un appareil, pour la liste des postes connectes.

    L'ecriture n'a pas lieu a chaque requete : une borne laissee ouverte
    interrogerait le disque en continu pour rien.
    """
    if not jeton:
        return
    with _verrou:
        entree = _tous().get(jeton)
        if entree is None:
            return
        maintenant = time.time()
        if maintenant - entree.get("vu_le", 0) > 60:
            entree["vu_le"] = maintenant
            _ecrire()


def oublier(jeton: str | None) -> bool:
    """Retire un appareil : il redemandera son role au prochain chargement."""
    if not jeton:
        return False
    with _verrou:
        if _tous().pop(jeton, None) is None:
            return False
        _ecrire()
        return True


def a_le_droit(jeton: str | None, droit: str) -> bool:
    role = role_de(jeton)
    return role is not None and droit in DROITS[role]


def accueil(jeton: str | None) -> str:
    role = role_de(jeton)
    return ROLES[role]["accueil"] if role else "/connexion"


def etat(jeton: str | None) -> dict:
    """Ce que les pages ont besoin de savoir sur l'appareil qui les affiche."""
    role = role_de(jeton)
    if role is None:
        return {"role": None, "droits": [], "accueil": "/connexion", "roles": _catalogue()}
    return {
        "role": role,
        "nom": ROLES[role]["nom"],
        "droits": sorted(DROITS[role]),
        "accueil": ROLES[role]["accueil"],
        "roles": _catalogue(),
    }


def _catalogue() -> list[dict]:
    return [{"cle": cle, **valeurs} for cle, valeurs in ROLES.items()]


def connectes(fenetre: float = 300.0) -> list[dict]:
    """Postes vus recemment, pour le tableau de bord."""
    limite = time.time() - fenetre
    return sorted(
        (
            {"role": e["role"], "nom": e.get("nom", ""), "vu_le": e.get("vu_le", 0)}
            for e in _tous().values()
            if e.get("vu_le", 0) >= limite
        ),
        key=lambda e: e["vu_le"],
        reverse=True,
    )


def compte() -> dict[str, int]:
    """Nombre d'appareils inscrits par role."""
    resultat = {cle: 0 for cle in ROLES}
    for entree in _tous().values():
        if entree["role"] in resultat:
            resultat[entree["role"]] += 1
    return resultat
