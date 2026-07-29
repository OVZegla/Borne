"""Reglages propres a chaque boutique : marque, catalogue, paiement.

Tout ce qu'un client peut personnaliser vit ici, dans un fichier JSON range a
cote de ses depots. Le code ne contient plus que des valeurs de depart : une
boutique peut creer ses propres matieres, ses propres formats, ses propres
coupes, ou couper entierement le menu des coupes si elle n'a pas la machine.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata

from . import config

# Geometries que la borne sait dessiner. Une coupe creee par la boutique porte
# son propre nom et son propre prix, mais s'appuie sur l'une d'elles.
GEOMETRIES = {
    "rectangle": "Rectangle (aucune découpe)",
    "cercle": "Cercle",
    "losange": "Losange / diamant",
    "triangle": "Triangle",
    "hexagone": "Hexagone",
    "arche": "Arche",
}

COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAUTS = {
    "boutique": {"nom": "", "logo": None},
    "theme": {"primaire": "#00287E", "accent": "#3D6FE0"},
    "catalogue": {
        "formes_actives": True,
        "matieres": [
            {"cle": "plexiglas", "nom": "Plexiglas", "coefficient": 1.80, "decoupe": True},
            {"cle": "metal", "nom": "Métal", "coefficient": 1.90, "decoupe": True},
            {"cle": "dibond", "nom": "Dibond", "coefficient": 1.60, "decoupe": True},
            {"cle": "toile", "nom": "Toile", "coefficient": 1.35, "decoupe": False},
            {"cle": "cadre", "nom": "Cadre", "coefficient": 1.50, "decoupe": True},
            {"cle": "papier", "nom": "Papier", "coefficient": 1.00, "decoupe": True},
            {"cle": "bois", "nom": "Bois", "coefficient": 1.70, "decoupe": True},
            {"cle": "verre", "nom": "Verre", "coefficient": 2.00, "decoupe": True},
        ],
        "formats": [
            {"cle": "25x30", "nom": "25×30", "largeur": 25, "hauteur": 30, "prix": 24.00},
            {"cle": "30x40", "nom": "30×40", "largeur": 30, "hauteur": 40, "prix": 32.00},
            {"cle": "40x50", "nom": "40×50", "largeur": 40, "hauteur": 50, "prix": 44.00},
            {"cle": "40x60", "nom": "40×60", "largeur": 40, "hauteur": 60, "prix": 49.00},
            {"cle": "50x70", "nom": "50×70", "largeur": 50, "hauteur": 70, "prix": 65.00},
            {"cle": "20x20", "nom": "20×20", "largeur": 20, "hauteur": 20, "prix": 19.00},
            {"cle": "30x30", "nom": "30×30", "largeur": 30, "hauteur": 30, "prix": 27.00},
            {"cle": "40x40", "nom": "40×40", "largeur": 40, "hauteur": 40, "prix": 38.00},
            {"cle": "50x50", "nom": "50×50", "largeur": 50, "hauteur": 50, "prix": 52.00},
        ],
        "formes": [
            {"cle": "initial", "nom": "Format initial", "geometrie": "rectangle", "supplement": 0.0},
            {"cle": "diamant", "nom": "Diamant", "geometrie": "losange", "supplement": 6.0},
            {"cle": "triangle", "nom": "Triangle", "geometrie": "triangle", "supplement": 6.0},
            {"cle": "cercle", "nom": "Cercle", "geometrie": "cercle", "supplement": 8.0},
        ],
    },
    "paiement": {
        "mode": "comptoir",   # « comptoir » ou « lien »
        "lien": "",
        "libelle": "",
    },
}

_verrou = threading.RLock()
_cache: dict | None = None


class ReglageError(ValueError):
    """Reglage refuse."""


def _fichier():
    return config.DATA_DIR / "reglages.json"


def _fusion(defaut, recu):
    """Complete les valeurs manquantes par les valeurs de depart."""
    if not isinstance(recu, dict):
        return json.loads(json.dumps(defaut))
    resultat = {}
    for cle, valeur in defaut.items():
        if isinstance(valeur, dict):
            resultat[cle] = _fusion(valeur, recu.get(cle))
        else:
            resultat[cle] = recu.get(cle, valeur)
    return resultat


def tout() -> dict:
    global _cache
    with _verrou:
        if _cache is None:
            try:
                _cache = _fusion(DEFAUTS, json.loads(_fichier().read_text("utf-8")))
            except (OSError, json.JSONDecodeError):
                _cache = json.loads(json.dumps(DEFAUTS))
        return _cache


def recharger() -> None:
    """Oublie le cache : utile apres une modification exterieure ou en test."""
    global _cache
    with _verrou:
        _cache = None


def _ecrire(valeurs: dict) -> dict:
    global _cache
    with _verrou:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _fichier().write_text(json.dumps(valeurs, ensure_ascii=False, indent=1), "utf-8")
        _cache = valeurs
        return valeurs


# --- validation ---------------------------------------------------------------


def cle_depuis(nom: str, prises: set[str]) -> str:
    """Fabrique un identifiant stable et lisible a partir d'un nom libre."""
    sans_accent = unicodedata.normalize("NFKD", nom)
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "-", sans_accent.lower()).strip("-") or "element"
    candidat, suffixe = base, 2
    while candidat in prises:
        candidat = f"{base}-{suffixe}"
        suffixe += 1
    return candidat


def _texte(valeur, champ: str, maxi: int = 60) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ReglageError(f"{champ} : le nom ne peut pas être vide")
    return texte[:maxi]


def _nombre(valeur, champ: str, mini: float, maxi: float) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        raise ReglageError(f"{champ} : valeur numérique attendue") from None
    if not (mini <= nombre <= maxi):
        raise ReglageError(f"{champ} : doit être compris entre {mini} et {maxi}")
    return round(nombre, 2)


def _valider_catalogue(recu: dict) -> dict:
    matieres, formats, formes = [], [], []

    prises: set[str] = set()
    for brut in recu.get("matieres") or []:
        nom = _texte(brut.get("nom"), "Matière")
        cle = str(brut.get("cle") or "").strip() or cle_depuis(nom, prises)
        prises.add(cle)
        matieres.append({
            "cle": cle,
            "nom": nom,
            "coefficient": _nombre(brut.get("coefficient", 1), f"Matière « {nom} »", 0.01, 100),
            "decoupe": bool(brut.get("decoupe", True)),
        })
    if not matieres:
        raise ReglageError("Il faut au moins une matière")

    prises = set()
    for brut in recu.get("formats") or []:
        nom = _texte(brut.get("nom"), "Format", 30)
        cle = str(brut.get("cle") or "").strip() or cle_depuis(nom, prises)
        prises.add(cle)
        formats.append({
            "cle": cle,
            "nom": nom,
            "largeur": int(_nombre(brut.get("largeur", 0), f"Format « {nom} » (largeur)", 1, 1000)),
            "hauteur": int(_nombre(brut.get("hauteur", 0), f"Format « {nom} » (hauteur)", 1, 1000)),
            "prix": _nombre(brut.get("prix", 0), f"Format « {nom} » (prix)", 0, 100000),
        })
    if not formats:
        raise ReglageError("Il faut au moins un format")

    prises = set()
    for brut in recu.get("formes") or []:
        nom = _texte(brut.get("nom"), "Coupe", 40)
        geometrie = str(brut.get("geometrie") or "rectangle")
        if geometrie not in GEOMETRIES:
            raise ReglageError(f"Coupe « {nom} » : géométrie inconnue")
        cle = str(brut.get("cle") or "").strip() or cle_depuis(nom, prises)
        prises.add(cle)
        formes.append({
            "cle": cle,
            "nom": nom,
            "geometrie": geometrie,
            "supplement": _nombre(brut.get("supplement", 0), f"Coupe « {nom} »", 0, 100000),
        })

    # Une coupe « sans découpe » est indispensable : c'est le tirage rectangulaire.
    if not any(f["geometrie"] == "rectangle" for f in formes):
        formes.insert(0, {"cle": "initial", "nom": "Format initial",
                          "geometrie": "rectangle", "supplement": 0.0})

    return {
        "formes_actives": bool(recu.get("formes_actives", True)),
        "matieres": matieres,
        "formats": formats,
        "formes": formes,
    }


def _valider_theme(recu: dict) -> dict:
    theme = {}
    for cle, defaut in DEFAUTS["theme"].items():
        valeur = str(recu.get(cle) or defaut).strip()
        if not COULEUR.match(valeur):
            raise ReglageError(f"Couleur « {cle} » : format attendu #RRGGBB")
        theme[cle] = valeur.upper()
    return theme


def _valider_paiement(recu: dict) -> dict:
    mode = str(recu.get("mode") or "comptoir")
    if mode not in ("comptoir", "lien"):
        raise ReglageError("Mode de paiement inconnu")
    lien = str(recu.get("lien") or "").strip()
    if mode == "lien":
        if not lien.startswith(("http://", "https://")):
            raise ReglageError("Le lien de paiement doit commencer par https://")
        if len(lien) > 500:
            raise ReglageError("Lien de paiement trop long")
    return {"mode": mode, "lien": lien, "libelle": str(recu.get("libelle") or "").strip()[:60]}


def enregistrer(recu: dict) -> dict:
    """Valide puis ecrit les reglages envoyes par la page d'administration."""
    if not isinstance(recu, dict):
        raise ReglageError("Réglages illisibles")

    courant = tout()
    boutique = recu.get("boutique") or {}
    valeurs = {
        "boutique": {
            "nom": str(boutique.get("nom") or "").strip()[:60],
            # Le logo se televerse a part : on ne l'ecrase pas ici.
            "logo": courant["boutique"].get("logo"),
        },
        "theme": _valider_theme(recu.get("theme") or {}),
        "catalogue": _valider_catalogue(recu.get("catalogue") or {}),
        "paiement": _valider_paiement(recu.get("paiement") or {}),
    }
    return _ecrire(valeurs)


def definir_logo(nom_fichier: str | None) -> dict:
    valeurs = json.loads(json.dumps(tout()))
    valeurs["boutique"]["logo"] = nom_fichier
    return _ecrire(valeurs)


def reinitialiser() -> dict:
    return _ecrire(json.loads(json.dumps(DEFAUTS)))
