"""Tableau de bord de la boutique : ce qu'un gerant regarde en arrivant.

Tout se calcule a la demande depuis les depots en cours : rien n'est archive, et
les chiffres portent donc sur la periode de conservation (24 h par defaut). Une
comptabilite au long cours n'est pas l'objet de ce module.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from . import catalogue, config, postes, reglages


def _debut_du_jour(horodatage: float) -> float:
    jour = datetime.fromtimestamp(horodatage)
    return jour.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def resume(store, maintenant: float | None = None) -> dict:
    """Chiffres, files d'attente et tendances, en une seule reponse."""
    maintenant = time.time() if maintenant is None else maintenant
    depots = [t for t in store.recent(limit=10_000) if t.validated]
    debut_jour = _debut_du_jour(maintenant)

    du_jour = [t for t in depots if (t.validated_at or t.created_at) >= debut_jour]
    encaisse = sum(t.total for t in du_jour if t.paid)
    attente = [t for t in depots if not t.paid]
    tirages = sum(len(t.images) for t in du_jour)

    return {
        "devise": catalogue.DEVISE,
        "maintenant": maintenant,
        "jour": {
            "depots": len(du_jour),
            "tirages": tirages,
            "encaisse": round(encaisse, 2),
            "attente": round(sum(t.total for t in attente), 2),
            "panier_moyen": round(encaisse / len(du_jour), 2) if du_jour else 0.0,
        },
        # Les deux files d'attente qui demandent une action au comptoir.
        "a_encaisser": [_ligne(t) for t in sorted(attente, key=lambda t: t.validated_at or 0)][:8],
        "a_retirer": [
            _ligne(t)
            for t in sorted(
                (t for t in depots if t.paid), key=lambda t: t.expires_at
            )
        ][:8],
        "expirent": [
            _ligne(t) for t in depots if t.expires_at - maintenant < 3 * 3600
        ][:8],
        "jours": _sept_jours(depots, maintenant),
        "supports": _classement(depots, "matiere"),
        "formats": _classement(depots, "format"),
        "postes": {"connectes": postes.connectes(), "inscrits": postes.compte()},
        "boutique": {
            "nom": reglages.tout()["boutique"].get("nom") or "",
            "retention_heures": config.RETENTION_HOURS,
            "paiement": reglages.tout()["paiement"],
        },
    }


def _ligne(ticket) -> dict:
    return {
        "code": ticket.code,
        "total": ticket.total,
        "tirages": len(ticket.images),
        "validated_at": ticket.validated_at,
        "expires_at": ticket.expires_at,
        "paiement": "paye" if ticket.paid else "en_attente",
        "apercu": next(
            (i.id for i in ticket.images if i.mime.startswith("image/")), None
        ),
    }


def _sept_jours(depots: list, maintenant: float) -> list[dict]:
    """Recette encaissee par jour, du plus ancien au plus recent."""
    aujourdhui = datetime.fromtimestamp(maintenant).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    jours = []
    for recul in range(6, -1, -1):
        debut = aujourdhui - timedelta(days=recul)
        fin = debut + timedelta(days=1)
        d0, d1 = debut.timestamp(), fin.timestamp()
        dedans = [
            t for t in depots if d0 <= (t.validated_at or t.created_at) < d1
        ]
        jours.append({
            "jour": debut.strftime("%Y-%m-%d"),
            "libelle": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"][debut.weekday()],
            "depots": len(dedans),
            "encaisse": round(sum(t.total for t in dedans if t.paid), 2),
        })
    return jours


def _classement(depots: list, champ: str, limite: int = 5) -> list[dict]:
    """Ce qui se vend le plus, en nombre de tirages et en recette."""
    noms = (
        {c: e["nom"] for c, e in catalogue.matieres().items()}
        if champ == "matiere"
        else {c: e["nom"] for c, e in catalogue.formats().items()}
    )
    compteur: dict[str, dict] = {}
    for ticket in depots:
        for image in ticket.images:
            if not image.article:
                continue
            cle = getattr(image.article, champ)
            entree = compteur.setdefault(
                cle, {"cle": cle, "nom": noms.get(cle, cle), "tirages": 0, "recette": 0.0}
            )
            entree["tirages"] += 1
            entree["recette"] += image.article.prix
    classement = sorted(compteur.values(), key=lambda e: e["tirages"], reverse=True)
    for entree in classement:
        entree["recette"] = round(entree["recette"], 2)
    return classement[:limite]
