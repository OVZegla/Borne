"""Calculs du catalogue : prix, libelles, validation d'un tirage.

Les donnees (matieres, formats, coupes, tarifs) ne sont plus ecrites ici : elles
appartiennent a chaque boutique et vivent dans `reglages.py`. Ce module ne fait
que les interroger.

Un tirage vaut : prix du format x coefficient de la matiere + supplement de coupe.
L'orientation ne change pas le prix, seulement le sens du cadre.

Presque tout se regle matiere par matiere : les formats proposes, les coupes
autorisees, le droit au sur-mesure et ses limites de taille, le droit a la forme
libre. La boutique garde un interrupteur general au-dessus : ce qu'elle coupe,
aucune matiere ne peut le rouvrir.
"""

from __future__ import annotations

from . import reglages

DEVISE = "€"

# Cles reservees : elles ne designent pas une entree du catalogue mais un choix
# libre du client, encadre par les reglages de la boutique.
SUR_MESURE = "__sur_mesure__"
FORME_LIBRE = "__libre__"

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


def sur_mesure() -> dict:
    """Reglage general du sur-mesure, valable pour toute la boutique."""
    return reglages.tout()["catalogue"].get("sur_mesure") or {"actif": False}


def forme_libre() -> dict:
    """Reglage general de la forme libre, valable pour toute la boutique."""
    return reglages.tout()["catalogue"].get("forme_libre") or {"actif": False}


# --- ce qu'une matiere donnee autorise ---------------------------------------


def formats_de(matiere: str) -> list[str]:
    """Cles des formats proposes pour cette matiere, dans l'ordre du catalogue."""
    retenus = matieres()[matiere].get("formats") or []
    toutes = list(formats())
    return [cle for cle in toutes if cle in retenus] if retenus else toutes


def formes_de(matiere: str) -> list[str]:
    """Cles des coupes proposees pour cette matiere."""
    entree = matieres()[matiere]
    table = formes()
    retenues = entree.get("formes") or []
    cles = [cle for cle in table if cle in retenues] if retenues else list(table)

    # Deux verrous au-dessus du choix de la matiere : la boutique peut avoir
    # coupe le menu, et la matiere peut ne pas se decouper du tout.
    if not formes_actives() or not entree.get("decoupe", True):
        cles = [cle for cle in cles if table[cle]["geometrie"] == "rectangle"]
        if not cles:
            cles = [forme_neutre()]
    return cles


def sur_mesure_de(matiere: str) -> dict:
    """Sur-mesure resolu pour une matiere : actif, taille mini, taille maxi."""
    general = sur_mesure()
    propre = matieres()[matiere].get("sur_mesure") or {}
    mini = propre.get("min_cm")
    maxi = propre.get("max_cm")
    return {
        "actif": bool(general.get("actif")) and bool(propre.get("actif", True)),
        "min_cm": int(mini if mini is not None else general.get("min_cm", 10)),
        "max_cm": int(maxi if maxi is not None else general.get("max_cm", 120)),
    }


def forme_libre_de(matiere: str) -> dict:
    """Forme libre resolue pour une matiere : active ou non, et son supplement."""
    general = forme_libre()
    propre = matieres()[matiere].get("forme_libre") or {}
    supplement = propre.get("supplement")
    actif = (
        bool(general.get("actif"))
        and bool(propre.get("actif", True))
        and formes_actives()
        and bool(matieres()[matiere].get("decoupe", True))
    )
    return {
        "actif": actif,
        "supplement": float(
            supplement if supplement is not None else general.get("supplement", 0)
        ),
    }


def forme_neutre() -> str:
    """La coupe rectangulaire, seule autorisee quand les coupes sont desactivees."""
    for cle, forme in formes().items():
        if forme["geometrie"] == "rectangle":
            return cle
    return next(iter(formes()), "initial")


def carre(format_: str) -> bool:
    entree = formats().get(format_)
    return bool(entree) and entree["largeur"] == entree["hauteur"]


def mesures_valides(matiere: str, largeur: float, hauteur: float) -> tuple[int, int]:
    """Controle des dimensions saisies par le client, selon les bornes de la matiere."""
    reglage = sur_mesure_de(matiere)
    if not reglage["actif"]:
        nom = matieres()[matiere]["nom"]
        raise CatalogueError(f"Le sur-mesure n'est pas propose pour {nom}")
    mini, maxi = reglage["min_cm"], reglage["max_cm"]
    try:
        largeur, hauteur = round(float(largeur)), round(float(hauteur))
    except (TypeError, ValueError):
        raise CatalogueError("Dimensions illisibles") from None
    for valeur in (largeur, hauteur):
        if not (mini <= valeur <= maxi):
            raise CatalogueError(f"Chaque cote doit mesurer entre {mini} et {maxi} cm")
    return int(largeur), int(hauteur)


def verifier(
    matiere: str,
    format_: str,
    forme: str,
    orientation: str = PORTRAIT,
    mesures: tuple[int, int] | None = None,
    points: list | None = None,
) -> None:
    """Leve CatalogueError si la combinaison n'est pas proposee par la boutique."""
    table_matieres, table_formats, table_formes = matieres(), formats(), formes()

    if matiere not in table_matieres:
        raise CatalogueError(f"Matiere inconnue : {matiere}")
    nom_matiere = table_matieres[matiere]["nom"]

    if format_ == SUR_MESURE:
        if mesures is None:
            raise CatalogueError("Dimensions sur mesure manquantes")
        mesures_valides(matiere, *mesures)
    elif format_ not in table_formats:
        raise CatalogueError(f"Format inconnu : {format_}")
    elif format_ not in formats_de(matiere):
        raise CatalogueError(f"Le format {table_formats[format_]['nom']} n'existe pas en {nom_matiere}")

    if forme == FORME_LIBRE:
        if not forme_libre_de(matiere)["actif"]:
            raise CatalogueError(f"La forme libre n'est pas proposee pour {nom_matiere}")
        if not isinstance(points, list) or len(points) < 3:
            raise CatalogueError("Le contour libre demande au moins trois points")
    elif forme not in table_formes:
        raise CatalogueError(f"Coupe inconnue : {forme}")
    elif forme not in formes_de(matiere):
        raise CatalogueError(f"La coupe {table_formes[forme]['nom']} n'est pas proposee en {nom_matiere}")

    if orientation not in ORIENTATIONS:
        raise CatalogueError(f"Orientation inconnue : {orientation}")


def _base(matiere: dict, format_: dict, mode: str) -> float:
    """Prix du tirage nu, avant supplement de coupe."""
    if mode == "surface":
        surface = (format_["largeur"] / 100) * (format_["hauteur"] / 100)
        return surface * matiere.get("prix_m2", 0)
    return format_["prix"] * matiere["coefficient"]


def prix(
    matiere: str,
    format_: str,
    forme: str,
    orientation: str = PORTRAIT,
    mesures: tuple[int, int] | None = None,
    points: list | None = None,
) -> float:
    """Prix TTC d'un tirage, arrondi au centime.

    L'orientation ne change rien : un 30x40 et un 40x30 ont la meme surface.
    """
    verifier(matiere, format_, forme, orientation, mesures, points)
    entree_matiere = matieres()[matiere]

    if format_ == SUR_MESURE:
        # Sans grille de prix pour des dimensions quelconques, seul le tarif au
        # metre carre a du sens : il s'applique quel que soit le mode choisi.
        largeur, hauteur = mesures_valides(matiere, *mesures)
        base = (largeur / 100) * (hauteur / 100) * entree_matiere.get("prix_m2", 0)
    else:
        base = _base(entree_matiere, formats()[format_], tarification())

    supplement = (
        forme_libre_de(matiere)["supplement"]
        if forme == FORME_LIBRE
        else formes()[forme]["supplement"]
    )
    return round(base + supplement, 2)


def dimensions(
    format_: str, orientation: str = PORTRAIT, mesures: tuple[int, int] | None = None
) -> tuple[int, int]:
    """Largeur et hauteur reelles du tirage, orientation comprise."""
    if format_ == SUR_MESURE:
        largeur, hauteur = (mesures or (0, 0))
    else:
        entree = formats()[format_]
        largeur, hauteur = entree["largeur"], entree["hauteur"]
    if orientation == PAYSAGE and largeur != hauteur:
        return hauteur, largeur
    return largeur, hauteur


def libelle(
    matiere: str,
    format_: str,
    forme: str,
    orientation: str = PORTRAIT,
    mesures: tuple[int, int] | None = None,
) -> str:
    """Description lisible d'un article, pour le poste de reception."""
    largeur, hauteur = dimensions(format_, orientation, mesures)
    morceaux = [matieres()[matiere]["nom"], f"{largeur}x{hauteur} cm"]
    if format_ == SUR_MESURE:
        morceaux.append("sur mesure")
    if forme == FORME_LIBRE:
        morceaux.append("forme libre")
    elif formes()[forme]["geometrie"] != "rectangle":
        morceaux.append(formes()[forme]["nom"])
    return " · ".join(morceaux)


def public() -> dict:
    """Catalogue complet envoye aux pages web.

    Tout ce qui depend de la matiere est deja resolu ici : la borne n'a plus
    qu'a lire les listes de la matiere choisie.
    """
    valeurs = reglages.tout()["catalogue"]
    mode = valeurs.get("tarification", "coefficient")
    table_formes = _index(valeurs["formes"])

    offertes: set[str] = set()  # coupes qu'au moins une matiere accepte
    matieres_publiques, grille = [], {}
    for matiere in valeurs["matieres"]:
        cle = matiere["cle"]
        cles_formats = formats_de(cle)
        cles_formes = formes_de(cle)
        offertes.update(cles_formes)
        matieres_publiques.append({
            "cle": cle,
            "nom": matiere["nom"],
            "formats": cles_formats,
            "formes": cles_formes,
            "prix_m2": matiere.get("prix_m2", 0),
            "sur_mesure": sur_mesure_de(cle),
            "forme_libre": forme_libre_de(cle),
        })
        for format_ in valeurs["formats"]:
            if format_["cle"] not in cles_formats:
                continue
            for forme in cles_formes:
                identifiant = f"{cle}|{format_['cle']}|{forme}"
                grille[identifiant] = round(
                    _base(matiere, format_, mode) + table_formes[forme]["supplement"], 2
                )

    return {
        "matieres": matieres_publiques,
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
        # Seules les coupes qu'au moins une matiere accepte : une boutique qui a
        # coupe le menu ne doit pas les voir passer.
        "formes": [
            {
                "cle": f["cle"],
                "nom": f["nom"],
                "geometrie": f["geometrie"],
                "supplement": f["supplement"],
                "points": f.get("points"),
            }
            for f in valeurs["formes"]
            if f["cle"] in offertes
        ],
        "formes_actives": bool(valeurs["formes_actives"]),
        "tarification": mode,
        "devise": DEVISE,
        "prix": grille,
    }
