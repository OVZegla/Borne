"""Activation par abonnement : connexion, licence signee, verification hors ligne.

Le serveur de licences delivre un jeton signe avec sa cle privee. L'application
n'embarque que la cle *publique* : elle peut donc verifier une licence sans
reseau, et personne ne peut en fabriquer une.

La verification RSA tient en quelques lignes de bibliotheque standard (`pow` et
`hashlib`), ce qui evite d'imposer une dependance aux postes en boutique. Seul
le serveur, que vous maitrisez, a besoin d'une vraie bibliotheque de crypto pour
*signer*.

Une licence reste valable hors ligne pendant un delai de grace : une coupure
Internet ne doit pas empecher une boutique de vendre.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import config

# Etats possibles, tels qu'ils sont montres a l'utilisateur.
ABSENTE = "absente"          # aucune connexion enregistree
VALIDE = "valide"            # abonnement actif, verifie recemment
GRACE = "grace"              # hors ligne, mais encore dans le delai tolere
EXPIREE = "expiree"          # abonnement termine ou delai de grace depasse
ALTEREE = "alteree"          # signature invalide : fichier bricole


class LicenceError(Exception):
    """Activation refusee."""


# --- verification RSA PKCS#1 v1.5 (SHA-256) -----------------------------------

# Prefixe DigestInfo d'un condensat SHA-256, cf. RFC 8017 section 9.2.
_DIGEST_INFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _entier(donnees: bytes) -> int:
    return int.from_bytes(donnees, "big")


def _lire_cle_publique(pem: str) -> tuple[int, int]:
    """Extrait (modulo, exposant) d'une cle publique PEM, sans dependance.

    On parcourt le DER a la main : SubjectPublicKeyInfo contient un BIT STRING
    qui enveloppe la sequence RSAPublicKey ::= { modulus, publicExponent }.
    """
    corps = "".join(l.strip() for l in pem.splitlines() if not l.startswith("-----"))
    der = base64.b64decode(corps)

    def lire_longueur(donnees: bytes, i: int) -> tuple[int, int]:
        premier = donnees[i]
        i += 1
        if premier < 0x80:
            return premier, i
        nombre = premier & 0x7F
        return _entier(donnees[i:i + nombre]), i + nombre

    def lire_element(donnees: bytes, i: int) -> tuple[int, bytes, int]:
        etiquette = donnees[i]
        longueur, i = lire_longueur(donnees, i + 1)
        return etiquette, donnees[i:i + longueur], i + longueur

    etiquette, contenu, _ = lire_element(der, 0)
    if etiquette != 0x30:
        raise LicenceError("Cle publique illisible")

    # SubjectPublicKeyInfo : on saute l'AlgorithmIdentifier puis on ouvre le BIT STRING.
    _, _, apres_algo = lire_element(contenu, 0)
    etiquette, bits, _ = lire_element(contenu, apres_algo)
    if etiquette == 0x03:
        interne = bits[1:]  # le premier octet compte les bits inutilises
    else:
        interne = contenu

    etiquette, sequence, _ = lire_element(interne, 0)
    if etiquette != 0x30:
        raise LicenceError("Cle publique illisible")
    _, modulo, apres = lire_element(sequence, 0)
    _, exposant, _ = lire_element(sequence, apres)
    return _entier(modulo), _entier(exposant)


def verifier_signature(charge: bytes, signature: bytes, pem: str) -> bool:
    """La signature correspond-elle a cette charge et a cette cle publique ?"""
    try:
        modulo, exposant = _lire_cle_publique(pem)
    except (LicenceError, ValueError, IndexError):
        return False

    taille = (modulo.bit_length() + 7) // 8
    if len(signature) != taille:
        return False

    clair = pow(_entier(signature), exposant, modulo).to_bytes(taille, "big")
    attendu = (
        b"\x00\x01"
        + b"\xff" * (taille - len(_DIGEST_INFO_SHA256) - hashlib.sha256().digest_size - 3)
        + b"\x00"
        + _DIGEST_INFO_SHA256
        + hashlib.sha256(charge).digest()
    )
    # Comparaison a temps constant : la signature est une donnee non fiable.
    import hmac

    return hmac.compare_digest(clair, attendu)


# --- licence stockee sur la machine -------------------------------------------


@dataclass
class Licence:
    charge: dict
    signature_b64: str
    verifiee_le: float

    @property
    def email(self) -> str:
        return self.charge.get("email", "")

    @property
    def atelier(self) -> str:
        return self.charge.get("atelier", "")

    @property
    def offre(self) -> str:
        return self.charge.get("offre", "")

    @property
    def expire_le(self) -> float:
        return float(self.charge.get("expire_le", 0))

    def etat(self, maintenant: float | None = None) -> str:
        maintenant = time.time() if maintenant is None else maintenant
        if not verifier_signature(
            json.dumps(self.charge, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            base64.b64decode(self.signature_b64),
            config.LICENCE_CLE_PUBLIQUE,
        ):
            return ALTEREE
        if maintenant > self.expire_le:
            return EXPIREE
        # Hors ligne trop longtemps : on redemande une confirmation au serveur.
        if maintenant - self.verifiee_le > config.LICENCE_GRACE_HEURES * 3600:
            return GRACE
        return VALIDE

    def public(self, maintenant: float | None = None) -> dict:
        etat = self.etat(maintenant)
        return {
            "etat": etat,
            "email": self.email,
            "atelier": self.atelier,
            "offre": self.offre,
            "expire_le": self.expire_le,
            "verifiee_le": self.verifiee_le,
            "utilisable": etat in (VALIDE, GRACE),
        }


def _fichier() -> "object":
    return config.DATA_DIR / "licence.json"


def charger() -> Licence | None:
    try:
        brut = json.loads(_fichier().read_text("utf-8"))
        return Licence(
            charge=brut["charge"],
            signature_b64=brut["signature"],
            verifiee_le=float(brut.get("verifiee_le", 0)),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def enregistrer(charge: dict, signature_b64: str) -> Licence:
    licence = Licence(charge=charge, signature_b64=signature_b64, verifiee_le=time.time())
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _fichier().write_text(
        json.dumps(
            {"charge": charge, "signature": signature_b64, "verifiee_le": licence.verifiee_le},
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )
    return licence


def oublier() -> None:
    try:
        _fichier().unlink()
    except OSError:
        pass


# --- dialogue avec le serveur de licences -------------------------------------


def activer(email: str, mot_de_passe: str, machine: str) -> Licence:
    """Echange les identifiants contre une licence signee."""
    if not config.LICENCE_URL:
        raise LicenceError("Aucun serveur de licences configure")

    corps = json.dumps(
        {"email": email, "mot_de_passe": mot_de_passe, "machine": machine}
    ).encode("utf-8")
    requete = urllib.request.Request(
        config.LICENCE_URL.rstrip("/") + "/api/activer",
        data=corps,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            recu = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8")).get("erreur")
        except Exception:
            message = None
        raise LicenceError(message or "Identifiants refuses") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LicenceError(
            "Serveur d'abonnement injoignable. Verifiez la connexion Internet."
        ) from exc
    except json.JSONDecodeError as exc:
        raise LicenceError("Reponse inattendue du serveur d'abonnement") from exc

    charge, signature = recu.get("charge"), recu.get("signature")
    if not isinstance(charge, dict) or not isinstance(signature, str):
        raise LicenceError("Licence incomplete renvoyee par le serveur")

    licence = Licence(charge=charge, signature_b64=signature, verifiee_le=time.time())
    etat = licence.etat()
    if etat == ALTEREE:
        raise LicenceError("Licence refusee : signature invalide")
    if etat == EXPIREE:
        raise LicenceError("Cet abonnement est expire")

    return enregistrer(charge, signature)


def rafraichir(machine: str) -> Licence | None:
    """Reconfirme silencieusement la licence aupres du serveur, si joignable."""
    licence = charger()
    if licence is None or not config.LICENCE_URL:
        return licence

    corps = json.dumps({"atelier": licence.atelier, "machine": machine}).encode("utf-8")
    requete = urllib.request.Request(
        config.LICENCE_URL.rstrip("/") + "/api/verifier",
        data=corps,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            recu = json.loads(reponse.read().decode("utf-8"))
    except Exception:
        return licence  # hors ligne : le delai de grace prend le relais

    charge, signature = recu.get("charge"), recu.get("signature")
    if isinstance(charge, dict) and isinstance(signature, str):
        candidate = Licence(charge=charge, signature_b64=signature, verifiee_le=time.time())
        if candidate.etat() != ALTEREE:
            return enregistrer(charge, signature)
    return licence


def etat_actuel() -> dict:
    """Resume affichable de la situation d'abonnement de cette machine."""
    if not config.LICENCE_URL:
        return {"etat": VALIDE, "utilisable": True, "abonnement_requis": False}

    licence = charger()
    if licence is None:
        return {"etat": ABSENTE, "utilisable": False, "abonnement_requis": True}
    return {**licence.public(), "abonnement_requis": True}


def atelier_effectif() -> str:
    """L'atelier qui appaire les machines.

    Des qu'un compte est connecte, c'est lui qui fait foi : deux postes ouverts
    avec le meme abonnement se trouvent sur le reseau, et seulement eux.
    """
    licence = charger()
    if licence is not None and licence.etat() in (VALIDE, GRACE) and licence.atelier:
        return licence.atelier
    return config.atelier()
