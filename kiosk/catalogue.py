"""Calculs du catalogue : prix, libelles, validation d'un tirage.

Les donnees (matieres, formats, coupes, tarifs) ne sont plus ecrites ici : elles
appartiennent a chaque boutique et vivent dans `reglages.py`. Ce module ne fait
que les interroger.

Un tirage vaut : prix du format x coefficient de la matiere + supplement de coupe.
L'orientation ne change pas le prix, seulement le sens du cadre.
"""

from __future__ import annotations

from . import reglages

DEVISE = "€"

PORTRAIT = "portrait"
PAYSAGE = "paysage"
ORIENTATIONS = (PORTRAIT, PAYSAGE)


class CatalogueError(ValueError):
    """Combinaison matiere / format / coupe impossible."""


def _index(entrees: list[dict]) -> dict[str, dict]:
    return {entree["cle"]: entree for entree in entrees}


def matieres() -> dict[str, dict]:
    return _index(reglages.tout()["catalogue"]["matieres"])


def formats() -> dict[str, dict]:
    return _index(reglages.tout()["catalogue"]["formats"])


def formes() -> dict[str, dict]:
    return _index(reglages.tout()["catalogue"]["formes"])


def tarification() -> str:
    return reglages.tout()["catalogue"].get("tarification", "coefficient")


def surface_m2(format_: str) -> float:
    """Surface du tirage en metres carres."""
    entree = formats()[format_]
    return (entree["largeur"] / 100) * (entree["hauteur"] / 100)


def formes_actives() -> bool:
    return bool(reglages.tout()["catalogue"]["formes_actives"])


def forme_neutre() -> str:
    """La coupe rectangulaire, seule autorisee quand les coupes sont desactivees."""
    for cle, forme in formes().items():
        if forme["geometrie"] == "rectangle":
            return cle
    return next(iter(formes()), "initial")


def carre(format_: str) -> bool:
    entree = formats().get(format_)
    return bool(entree) and entree["largeur"] == entree["hauteur"]


def verifier(matiere: str, format_: str, forme: str, orientation: str = PORTRAIT) -> None:
    """Leve CatalogueError si la combinaison n'est pas proposee par la boutique."""
    table_matieres, table_formats, table_formes = matieres(), formats(), formes()

    if matiere not in table_matieres:
        raise CatalogueError(f"Matiere inconnue : {matiere}")
    if format_ not in table_formats:
        raise CatalogueError(f"Format inconnu : {format_}")
    if forme not in table_formes:
        raise CatalogueError(f"Coupe inconnue : {forme}")
    if orientation not in ORIENTATIONS:
        raise CatalogueError(f"Orientation inconnue : {orientation}")

    rectangulaire = table_formes[forme]["geometrie"] == "rectangle"
    if not formes_actives() and not rectangulaire:
        raise CatalogueError("Les decoupes ne sont pas proposees par cette boutique")
    if not table_matieres[matiere]["decoupe"] and not rectangulaire:
        nom = table_matieres[matiere]["nom"]
        raise CatalogueError(f"La matiere {nom} ne se decoupe pas")


def _base(matiere: dict, format_: dict, mode: str) -> float:
    """Prix du tirage nu, avant supplement de coupe."""
    if mode == "surface":
        surface = (format_["largeur"] / 100) * (format_["hauteur"] / 100)
        return surface * matiere.get("prix_m2", 0)
    return format_["prix"] * matiere["coefficient"]


def prix(matiere: str, format_: str, forme: str, orientation: str = PORTRAIT) -> float:
    """Prix TTC d'un tirage, arrondi au centime.

    L'orientation ne change rien : un 30x40 et un 40x30 ont la meme surface.
    """
    verifier(matiere, format_, forme, orientation)
    base = _base(matieres()[matiere], formats()[format_], tarification())
    return round(base + formes()[forme]["supplement"], 2)


def dimensions(format_: str, orientation: str = PORTRAIT) -> tuple[int, int]:
    """Largeur et hauteur reelles du tirage, orientation comprise."""
    entree = formats()[format_]
    largeur, hauteur = entree["largeur"], entree["hauteur"]
    if orientation == PAYSAGE and largeur != hauteur:
        return hauteur, largeur
    return largeur, hauteur


def libelle(matiere: str, format_: str, forme: str, orientation: str = PORTRAIT) -> str:
    """Description lisible d'un article, pour le poste de reception."""
    largeur, hauteur = dimensions(format_, orientation)
    morceaux = [matieres()[matiere]["nom"], f"{largeur}x{hauteur} cm"]
    if formes()[forme]["geometrie"] != "rectangle":
        morceaux.append(formes()[forme]["nom"])
    return " · ".join(morceaux)


def public() -> dict:
    """Catalogue complet envoye aux pages web."""
    valeurs = reglages.tout()["catalogue"]
    actives = bool(valeurs["formes_actives"])
    liste_formes = [
        f for f in valeurs["formes"] if actives or f["geometrie"] == "rectangle"
    ]

    mode = valeurs.get("tarification", "coefficient")
    grille = {}
    for matiere in valeurs["matieres"]:
        for format_ in valeurs["formats"]:
            for forme in liste_formes:
                if forme["geometrie"] != "rectangle" and not matiere["decoupe"]:
                    continue
                cle = f"{matiere['cle']}|{format_['cle']}|{forme['cle']}"
                grille[cle] = round(_base(matiere, format_, mode) + forme["supplement"], 2)

    return {
        "matieres": [
            {"cle": m["cle"], "nom": m["nom"], "formes": bool(m["decoupe"])}
            for m in valeurs["matieres"]
        ],
        "formats": [
            {
                "cle": f["cle"],
                "nom": f"{f['nom']} cm",
                "largeur": f["largeur"],
                "hauteur": f["hauteur"],
                "carre": f["largeur"] == f["hauteur"],
            }
            for f in valeurs["formats"]
        ],
        "formes": [
            {
                "cle": f["cle"],
                "nom": f["nom"],
                "geometrie": f["geometrie"],
                "points": f.get("points"),
            }
            for f in liste_formes
        ],
        "formes_actives": actives,
        "tarification": mode,
        "devise": DEVISE,
        "prix": grille,
    }
