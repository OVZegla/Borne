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
from urllib.parse import urlparse

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
    "personnalise": "Forme dessinée",
}

# Deux facons de tarifer, au choix de la boutique.
TARIFICATIONS = {
    "coefficient": "Prix fixe par format, multiplie par la matiere",
    "surface": "Prix au metre carre, propre a chaque matiere",
}

COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAUTS = {
    "boutique": {"nom": "", "logo": None},
    # Trois couleurs suffisent : le reste de la palette (surfaces, texte, traits)
    # en est deduit, y compris le passage en clair ou en sombre selon le fond.
    "theme": {"primaire": "#00287E", "accent": "#3D6FE0", "fond": "#F2F6FD"},
    "catalogue": {
        "tarification": "coefficient",
        "formes_actives": True,
        # Les deux blocs ci-dessous sont les interrupteurs generaux de la
        # boutique, et les valeurs par defaut de chaque matiere. Une matiere
        # peut se retirer du jeu ou imposer ses propres bornes ; elle ne peut
        # pas proposer une option que la boutique a coupee.
        #
        # Dimensions libres saisies par le client sur la borne. Toujours
        # facturees au metre carre : c'est la seule regle qui tienne sans
        # grille de prix.
        "sur_mesure": {
            "actif": False,
            "min_cm": 10,
            "max_cm": 120,
        },
        # Contour dessine par le client lui-meme.
        "forme_libre": {
            "actif": False,
            "supplement": 12.0,
        },
        "matieres": [
            {"cle": "plexiglas", "nom": "Plexiglas", "coefficient": 1.80, "prix_m2": 480.0, "decoupe": True},
            {"cle": "metal", "nom": "Métal", "coefficient": 1.90, "prix_m2": 505.0, "decoupe": True},
            {"cle": "dibond", "nom": "Dibond", "coefficient": 1.60, "prix_m2": 425.0, "decoupe": True},
            {"cle": "toile", "nom": "Toile", "coefficient": 1.35, "prix_m2": 360.0, "decoupe": False},
            {"cle": "cadre", "nom": "Cadre", "coefficient": 1.50, "prix_m2": 400.0, "decoupe": True},
            {"cle": "papier", "nom": "Papier", "coefficient": 1.00, "prix_m2": 265.0, "decoupe": True},
            {"cle": "bois", "nom": "Bois", "coefficient": 1.70, "prix_m2": 450.0, "decoupe": True},
            {"cle": "verre", "nom": "Verre", "coefficient": 2.00, "prix_m2": 530.0, "decoupe": True},
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
        # Quand le client paie : « apres » lui donne le code et le QR de reglement
        # ensemble, « avant » garde le code cache jusqu'a l'encaissement.
        "ordre": "apres",
        "lien": "",
        "libelle": "",
    },
    # Depot depuis n'importe quel reseau : l'adresse publique du tunnel de la
    # boutique. Vide ou inactif, le QR code garde l'adresse du reseau local et
    # le depot reste reserve aux telephones poses sur le Wi-Fi de la boutique.
    "acces_distant": {"actif": False, "url": ""},
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


def _sous_ensemble(recu, connues: list[str]) -> list[str]:
    """Liste de cles retenue par une matiere ; vide veut dire « toutes ».

    Une entree supprimee du catalogue disparait d'elle-meme des matieres qui la
    citaient ; s'il ne reste plus rien, la matiere revient a « toutes » plutot
    que de bloquer l'enregistrement sur un reglage devenu caduc.
    """
    if not isinstance(recu, list):
        return []
    gardees = [cle for cle in connues if cle in set(map(str, recu))]
    return [] if len(gardees) in (0, len(connues)) else gardees


def _valider_catalogue(recu: dict) -> dict:
    matieres, formats, formes = [], [], []

    prises: set[str] = set()
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
        entree = {
            "cle": cle,
            "nom": nom,
            "geometrie": geometrie,
            "supplement": _nombre(brut.get("supplement", 0), f"Coupe « {nom} »", 0, 100000),
        }
        if geometrie == "personnalise":
            entree["points"] = _valider_points(brut.get("points"), nom)
        formes.append(entree)

    # Une coupe « sans découpe » est indispensable : c'est le tirage rectangulaire.
    if not any(f["geometrie"] == "rectangle" for f in formes):
        formes.insert(0, {"cle": "initial", "nom": "Format initial",
                          "geometrie": "rectangle", "supplement": 0.0})

    tarification = str(recu.get("tarification") or "coefficient")
    if tarification not in TARIFICATIONS:
        raise ReglageError("Mode de tarification inconnu")

    sur_mesure = recu.get("sur_mesure") or {}
    mini = int(_nombre(sur_mesure.get("min_cm", 10), "Sur mesure (minimum)", 1, 1000))
    maxi = int(_nombre(sur_mesure.get("max_cm", 120), "Sur mesure (maximum)", 1, 1000))
    if mini >= maxi:
        raise ReglageError("Sur mesure : le minimum doit être inférieur au maximum")

    libre = recu.get("forme_libre") or {}

    # Les matieres viennent en dernier : chacune renvoie aux formats et aux
    # coupes qu'on vient de valider, et herite des bornes generales.
    cles_formats = [f["cle"] for f in formats]
    cles_formes = [f["cle"] for f in formes]
    prises = set()
    for brut in recu.get("matieres") or []:
        nom = _texte(brut.get("nom"), "Matière")
        cle = str(brut.get("cle") or "").strip() or cle_depuis(nom, prises)
        prises.add(cle)
        matieres.append({
            "cle": cle,
            "nom": nom,
            "coefficient": _nombre(brut.get("coefficient", 1), f"Matière « {nom} » (coefficient)", 0.01, 100),
            "prix_m2": _nombre(brut.get("prix_m2", 0), f"Matière « {nom} » (prix au m²)", 0, 100000),
            "decoupe": bool(brut.get("decoupe", True)),
            # Vide = « tous », pour qu'un format ajoute plus tard soit propose
            # partout sans avoir a rouvrir chaque matiere.
            "formats": _sous_ensemble(brut.get("formats"), cles_formats),
            "formes": _sous_ensemble(brut.get("formes"), cles_formes),
            "sur_mesure": _valider_sur_mesure(brut.get("sur_mesure"), nom, mini, maxi),
            "forme_libre": _valider_forme_libre(brut.get("forme_libre"), nom),
        })
    if not matieres:
        raise ReglageError("Il faut au moins une matière")

    return {
        "tarification": tarification,
        "formes_actives": bool(recu.get("formes_actives", True)),
        "sur_mesure": {
            "actif": bool(sur_mesure.get("actif", False)),
            "min_cm": mini,
            "max_cm": maxi,
        },
        "forme_libre": {
            "actif": bool(libre.get("actif", False)),
            "supplement": _nombre(libre.get("supplement", 0), "Forme libre", 0, 100000),
        },
        "matieres": matieres,
        "formats": formats,
        "formes": formes,
    }


def _valider_sur_mesure(recu, nom: str, mini_boutique: int, maxi_boutique: int) -> dict:
    """Bornes propres a une matiere ; `None` veut dire « celles de la boutique ».

    Le verre ne se coupe pas au-dela d'un certain format, le papier si : chaque
    matiere doit pouvoir imposer sa propre limite de taille.
    """
    recu = recu if isinstance(recu, dict) else {}
    resultat = {"actif": bool(recu.get("actif", True)), "min_cm": None, "max_cm": None}
    for champ, general in (("min_cm", mini_boutique), ("max_cm", maxi_boutique)):
        valeur = recu.get(champ)
        if valeur in (None, ""):
            continue
        resultat[champ] = int(_nombre(valeur, f"Matière « {nom} » ({champ})", 1, 1000))
    mini = resultat["min_cm"] if resultat["min_cm"] is not None else mini_boutique
    maxi = resultat["max_cm"] if resultat["max_cm"] is not None else maxi_boutique
    if mini >= maxi:
        raise ReglageError(f"Matière « {nom} » : la taille minimum doit être inférieure au maximum")
    return resultat


def _valider_forme_libre(recu, nom: str) -> dict:
    """Forme libre matiere par matiere ; supplement `None` = celui de la boutique."""
    recu = recu if isinstance(recu, dict) else {}
    supplement = recu.get("supplement")
    return {
        "actif": bool(recu.get("actif", True)),
        "supplement": (
            None if supplement in (None, "")
            else _nombre(supplement, f"Matière « {nom} » (forme libre)", 0, 100000)
        ),
    }


def _valider_points(recu, nom: str) -> list[list[float]]:
    """Contour d'une forme dessinee, en pourcentages du cadre."""
    if not isinstance(recu, list) or len(recu) < 3:
        raise ReglageError(f"Coupe « {nom} » : il faut au moins trois points")
    if len(recu) > 60:
        raise ReglageError(f"Coupe « {nom} » : 60 points au maximum")
    points = []
    for point in recu:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ReglageError(f"Coupe « {nom} » : point illisible")
        x, y = (max(0.0, min(100.0, round(float(v), 2))) for v in point)
        points.append([x, y])
    return points


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
    ordre = str(recu.get("ordre") or "apres")
    if ordre not in ("avant", "apres"):
        raise ReglageError("Ordre de paiement inconnu")
    lien = str(recu.get("lien") or "").strip()
    if mode == "lien":
        if not lien.startswith(("http://", "https://")):
            raise ReglageError("Le lien de paiement doit commencer par https://")
        if len(lien) > 500:
            raise ReglageError("Lien de paiement trop long")
    return {
        "mode": mode,
        "ordre": ordre,
        "lien": lien,
        "libelle": str(recu.get("libelle") or "").strip()[:60],
    }


def _valider_acces_distant(recu: dict) -> dict:
    """L'adresse publique du tunnel : une origine https, et rien de plus.

    Le serveur ne sait servir que depuis la racine, et l'adresse part telle
    quelle dans un QR code : un chemin, une requete ou un fragment y seraient
    silencieusement perdus. On les refuse plutot que de livrer un QR mort.
    """
    url = str(recu.get("url") or "").strip().rstrip("/")
    actif = bool(recu.get("actif"))
    if not url:
        return {"actif": False, "url": ""}
    if len(url) > 200:
        raise ReglageError("Adresse de dépôt à distance trop longue")

    decoupe = urlparse(url)
    if decoupe.scheme != "https":
        raise ReglageError(
            "L'adresse de dépôt à distance doit commencer par https:// — "
            "un appareil photo de téléphone est refusé sur une page non sécurisée"
        )
    if not decoupe.hostname:
        raise ReglageError("Adresse de dépôt à distance incomplète")
    if decoupe.path or decoupe.query or decoupe.fragment:
        raise ReglageError(
            "L'adresse de dépôt à distance doit s'arrêter au nom de domaine, "
            "sans chemin ni paramètre"
        )
    return {"actif": actif, "url": url}


def url_publique() -> str:
    """Adresse a mettre dans les QR codes, ou une chaine vide si le depot a
    distance n'est pas ouvert.

    La variable d'environnement l'emporte : elle sert aux installations pilotees
    par un script, ou le fichier de reglages n'est pas edite a la main.
    """
    impose = config.PUBLIC_URL
    if impose:
        return impose.rstrip("/")
    distant = tout()["acces_distant"]
    return distant["url"] if distant.get("actif") and distant.get("url") else ""


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
        "acces_distant": _valider_acces_distant(recu.get("acces_distant") or {}),
    }
    return _ecrire(valeurs)


def definir_logo(nom_fichier: str | None) -> dict:
    valeurs = json.loads(json.dumps(tout()))
    valeurs["boutique"]["logo"] = nom_fichier
    return _ecrire(valeurs)


def reinitialiser() -> dict:
    return _ecrire(json.loads(json.dumps(DEFAUTS)))
