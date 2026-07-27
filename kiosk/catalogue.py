"""Catalogue produit : matieres, formats, formes et tarifs.

=============================================================================
  LES PRIX CI-DESSOUS SONT DES VALEURS DE DEPART, A REMPLACER PAR LES VOTRES.
  Tout se regle dans ce fichier : PRIX_FORMAT, COEFFICIENT_MATIERE et
  SUPPLEMENT_FORME. Aucun autre fichier n'a besoin d'etre touche.
=============================================================================
"""

from __future__ import annotations

# --- matieres ----------------------------------------------------------------
# "formes" indique si le client peut decouper la photo (la toile se tend sur un
# chassis : elle garde toujours son format d'origine).

MATIERES = {
    "plexiglas": {"nom": "Plexiglas", "formes": True},
    "metal": {"nom": "Métal", "formes": True},
    "dibond": {"nom": "Dibond", "formes": True},
    "toile": {"nom": "Toile", "formes": False},
    "cadre": {"nom": "Cadre", "formes": True},
    "papier": {"nom": "Papier", "formes": True},
    "bois": {"nom": "Bois", "formes": True},
    "verre": {"nom": "Verre", "formes": True},
}

# --- formats (en centimetres) ------------------------------------------------

FORMATS = {
    "25x30": {"largeur": 25, "hauteur": 30},
    "30x40": {"largeur": 30, "hauteur": 40},
    "40x50": {"largeur": 40, "hauteur": 50},
    "40x60": {"largeur": 40, "hauteur": 60},
    "50x70": {"largeur": 50, "hauteur": 70},
    "20x20": {"largeur": 20, "hauteur": 20},
    "30x30": {"largeur": 30, "hauteur": 30},
    "40x40": {"largeur": 40, "hauteur": 40},
    "50x50": {"largeur": 50, "hauteur": 50},
}

# --- formes ------------------------------------------------------------------

FORMES = {
    "initial": {"nom": "Format initial"},
    "diamant": {"nom": "Diamant"},
    "triangle": {"nom": "Triangle"},
    "cercle": {"nom": "Cercle"},
}

# --- tarifs ------------------------------------------------------------------
# Prix de base par format, en euros, pour la matiere de reference (papier).

PRIX_FORMAT = {
    "20x20": 19.00,
    "25x30": 24.00,
    "30x30": 27.00,
    "30x40": 32.00,
    "40x40": 38.00,
    "40x50": 44.00,
    "40x60": 49.00,
    "50x50": 52.00,
    "50x70": 65.00,
}

# Multiplicateur applique au prix de base selon la matiere.
COEFFICIENT_MATIERE = {
    "papier": 1.00,
    "toile": 1.35,
    "cadre": 1.50,
    "dibond": 1.60,
    "bois": 1.70,
    "plexiglas": 1.80,
    "metal": 1.90,
    "verre": 2.00,
}

# Supplement fixe pour une decoupe autre que le format initial.
SUPPLEMENT_FORME = {
    "initial": 0.00,
    "diamant": 6.00,
    "triangle": 6.00,
    "cercle": 8.00,
}

DEVISE = "€"


class CatalogueError(ValueError):
    """Combinaison matiere / format / forme impossible."""


def verifier(matiere: str, format_: str, forme: str) -> None:
    """Leve CatalogueError si la combinaison n'existe pas au catalogue."""
    if matiere not in MATIERES:
        raise CatalogueError(f"Matiere inconnue : {matiere}")
    if format_ not in FORMATS:
        raise CatalogueError(f"Format inconnu : {format_}")
    if forme not in FORMES:
        raise CatalogueError(f"Forme inconnue : {forme}")
    if not MATIERES[matiere]["formes"] and forme != "initial":
        nom = MATIERES[matiere]["nom"]
        raise CatalogueError(f"La matiere {nom} ne se decoupe pas : forme 'initial' uniquement")


def prix(matiere: str, format_: str, forme: str) -> float:
    """Prix TTC d'un tirage, arrondi au centime."""
    verifier(matiere, format_, forme)
    base = PRIX_FORMAT[format_] * COEFFICIENT_MATIERE[matiere]
    return round(base + SUPPLEMENT_FORME[forme], 2)


def libelle(matiere: str, format_: str, forme: str) -> str:
    """Description lisible d'un article, pour le poste de reception."""
    morceaux = [MATIERES[matiere]["nom"], f"{format_} cm"]
    if forme != "initial":
        morceaux.append(FORMES[forme]["nom"])
    return " · ".join(morceaux)


def public() -> dict:
    """Catalogue complet envoye aux pages web."""
    return {
        "matieres": [
            {"cle": cle, "nom": valeur["nom"], "formes": valeur["formes"]}
            for cle, valeur in MATIERES.items()
        ],
        "formats": [
            {
                "cle": cle,
                "nom": f"{valeur['largeur']}×{valeur['hauteur']} cm",
                "largeur": valeur["largeur"],
                "hauteur": valeur["hauteur"],
                "carre": valeur["largeur"] == valeur["hauteur"],
            }
            for cle, valeur in FORMATS.items()
        ],
        "formes": [{"cle": cle, "nom": valeur["nom"]} for cle, valeur in FORMES.items()],
        "devise": DEVISE,
        # La grille complete permet a la borne d'afficher le prix sans aller-retour.
        "prix": {
            f"{matiere}|{format_}|{forme}": prix(matiere, format_, forme)
            for matiere in MATIERES
            for format_ in FORMATS
            for forme in FORMES
            if MATIERES[matiere]["formes"] or forme == "initial"
        },
    }
