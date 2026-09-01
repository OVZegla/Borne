"""Stockage des depots.

Un depot vit en deux temps :
  1. session -- le telephone envoie des photos via un jeton secret (celui du QR
     code affiche sur la borne). Le depot est encore un brouillon.
  2. depot valide -- l'operateur valide sur la borne, un code a 4 chiffres est
     alors revele et sert au retrait cote imprimante.

Le code n'est jamais expose avant la validation : le jeton et le code sont deux
secrets distincts.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import catalogue, config, imagemeta


class StorageError(Exception):
    """Depot invalide ou refuse."""


@dataclass
class Article:
    """Le tirage commande pour une photo : matiere, format, coupe, orientation."""

    matiere: str
    format: str
    forme: str
    prix: float
    orientation: str = catalogue.PORTRAIT
    mesures: list | None = None   # dimensions sur mesure, en cm
    points: list | None = None    # contour dessine par le client

    @property
    def _mesures(self) -> tuple[int, int] | None:
        return tuple(self.mesures) if self.mesures else None

    def public(self) -> dict:
        data = asdict(self)
        try:
            data["libelle"] = catalogue.libelle(
                self.matiere, self.format, self.forme, self.orientation, self._mesures
            )
            largeur, hauteur = catalogue.dimensions(
                self.format, self.orientation, self._mesures
            )
            data["largeur"], data["hauteur"] = largeur, hauteur
        except (KeyError, catalogue.CatalogueError):
            # La boutique a pu retirer cette matiere ou ce format depuis la commande.
            data["libelle"] = f"{self.matiere} · {self.format}"
            data["largeur"] = data["hauteur"] = None
        return data


@dataclass
class Image:
    id: str
    name: str
    mime: str
    size: int
    filename: str
    created_at: float
    width: int | None = None
    height: int | None = None
    article: Article | None = None

    def public(self) -> dict:
        data = asdict(self)
        data.pop("filename")
        data["article"] = self.article.public() if self.article else None
        return data


@dataclass
class Ticket:
    code: str
    token: str
    payment_token: str
    created_at: float
    expires_at: float
    validated_at: float | None = None
    paid_at: float | None = None
    images: list[Image] = field(default_factory=list)

    @property
    def validated(self) -> bool:
        return self.validated_at is not None

    @property
    def paid(self) -> bool:
        return self.paid_at is not None

    @property
    def total(self) -> float:
        return round(sum(i.article.prix for i in self.images if i.article), 2)

    @property
    def configured(self) -> bool:
        """Toutes les photos ont-elles un tirage choisi ?"""
        return bool(self.images) and all(image.article for image in self.images)

    def _commun(self) -> dict:
        return {
            "created_at": self.created_at,
            "validee": self.validated,
            "paiement": "paye" if self.paid else "en_attente",
            "paid_at": self.paid_at,
            "total": self.total,
            "devise": catalogue.DEVISE,
            "images": [image.public() for image in self.images],
        }

    def public(self) -> dict:
        """Vue destinee au poste de reception : le code y figure."""
        return {
            **self._commun(),
            "code": self.code,
            "expires_at": self.expires_at,
            "validated_at": self.validated_at,
        }

    def session(self, code_visible: bool = True) -> dict:
        """Vue destinee a la borne et au telephone : pas de code avant validation.

        `code_visible` retombe a False quand la boutique fait payer d'abord : le
        code de retrait n'est alors delivre qu'une fois le reglement encaisse.
        """
        data = {**self._commun(), "token": self.token, "complete": self.configured}
        if self.validated:
            data["code_bloque"] = not code_visible
            if code_visible:
                data["code"] = self.code
        return data

    def paiement(self) -> dict:
        """Vue de la page de reglement : le montant, jamais le code de retrait."""
        return {
            "jeton": self.payment_token,
            "paiement": "paye" if self.paid else "en_attente",
            "paid_at": self.paid_at,
            "total": self.total,
            "devise": catalogue.DEVISE,
            "articles": [
                {
                    "nom": image.name,
                    "image_id": image.id,
                    "mime": image.mime,
                    **image.article.public(),
                }
                for image in self.images
                if image.article
            ],
        }


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-()\[\]]+")


def clean_name(name: str, fallback: str = "image") -> str:
    """Ramene un nom de fichier client a quelque chose d'inoffensif."""
    name = os.path.basename(name or "").strip()
    name = _SAFE_NAME.sub("_", name)[:120]
    return name or fallback


class Store:
    """Index JSON + fichiers sur disque, protege par un verrou."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tickets: dict[str, Ticket] = {}
        self._by_token: dict[str, Ticket] = {}
        self._by_payment: dict[str, Ticket] = {}
        self._load()

    @staticmethod
    def _assurer_dossier() -> None:
        """Cree l'arborescence au premier ecrit, pas a la construction : un poste
        qui ne fait que rejoindre un hote ne doit rien laisser sur son disque."""
        config.FILES_DIR.mkdir(parents=True, exist_ok=True)

    # --- persistance ---------------------------------------------------

    def _load(self) -> None:
        if not config.INDEX_FILE.exists():
            return
        try:
            raw = json.loads(config.INDEX_FILE.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for entry in raw.get("tickets", []):
            try:
                images = []
                for brut in entry.get("images", []):
                    article = brut.pop("article", None)
                    brut.pop("libelle", None)
                    image = Image(**brut)
                    if article:
                        article.pop("libelle", None)
                        image.article = Article(**article)
                    images.append(image)
                ticket = Ticket(
                    code=entry["code"],
                    token=entry["token"],
                    payment_token=entry["payment_token"],
                    created_at=entry["created_at"],
                    expires_at=entry["expires_at"],
                    validated_at=entry.get("validated_at"),
                    paid_at=entry.get("paid_at"),
                    images=images,
                )
            except (KeyError, TypeError):
                continue
            self._tickets[ticket.code] = ticket
            self._by_token[ticket.token] = ticket
            self._by_payment[ticket.payment_token] = ticket

    def _save(self) -> None:
        self._assurer_dossier()
        payload = {
            "version": 3,
            "tickets": [
                {
                    "code": t.code,
                    "token": t.token,
                    "payment_token": t.payment_token,
                    "created_at": t.created_at,
                    "expires_at": t.expires_at,
                    "validated_at": t.validated_at,
                    "paid_at": t.paid_at,
                    "images": [asdict(i) for i in t.images],
                }
                for t in self._tickets.values()
            ],
        }
        tmp = config.INDEX_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(config.INDEX_FILE)

    # --- lecture -------------------------------------------------------

    def get(self, code: str) -> Ticket | None:
        """Depot valide correspondant a un code de retrait."""
        with self._lock:
            self.purge()
            ticket = self._tickets.get(code)
            return ticket if ticket is not None and ticket.validated else None

    def get_by_token(self, token: str) -> Ticket | None:
        """Session en cours, validee ou non, identifiee par son jeton secret."""
        with self._lock:
            self.purge()
            return self._by_token.get(token)

    def get_by_payment(self, jeton: str) -> Ticket | None:
        """Commande a regler, identifiee par le jeton du QR code de paiement."""
        with self._lock:
            self.purge()
            return self._by_payment.get(jeton)

    def recent(self, limit: int = 30) -> list[Ticket]:
        """Depots proposes au retrait : uniquement ceux valides sur la borne."""
        with self._lock:
            self.purge()
            valides = [t for t in self._tickets.values() if t.validated]
            valides.sort(key=lambda t: t.validated_at or t.created_at, reverse=True)
            return valides[:limit]

    def find_image(self, image_id: str) -> tuple[Ticket, Image] | None:
        with self._lock:
            self.purge()
            for ticket in self._tickets.values():
                for image in ticket.images:
                    if image.id == image_id:
                        return ticket, image
        return None

    def path_of(self, image: Image) -> Path:
        return config.FILES_DIR / image.filename

    # --- ecriture ------------------------------------------------------

    def create_ticket(self) -> Ticket:
        """Ouvre une session : le jeton part dans le QR, le code reste cache.

        Les deux jetons font 16 octets, soit 128 bits. Sur le seul reseau local
        la moitie aurait suffi ; ouverts sur Internet par le tunnel, ils sont
        le seul secret qui protege les photos d'un client et le detail de sa
        commande, et se retrouvent exposes a un devinage sans limite de debit.
        """
        with self._lock:
            self.purge()
            now = time.time()
            ticket = Ticket(
                code=self._new_code(),
                token=secrets.token_urlsafe(16),
                payment_token=secrets.token_urlsafe(16),
                created_at=now,
                expires_at=now + config.RETENTION_HOURS * 3600,
            )
            self._tickets[ticket.code] = ticket
            self._by_token[ticket.token] = ticket
            self._by_payment[ticket.payment_token] = ticket
            self._save()
            return ticket

    def set_article(
        self,
        token: str,
        image_id: str,
        matiere: str,
        format_: str,
        forme: str,
        orientation: str = catalogue.PORTRAIT,
        mesures: list | None = None,
        points: list | None = None,
    ) -> Image:
        """Choisit le tirage d'une photo et calcule son prix."""
        with self._lock:
            ticket = self.get_by_token(token)
            if ticket is None:
                raise StorageError("Session inconnue ou expiree")
            if ticket.validated:
                raise StorageError("Ce depot est deja valide, la commande n'est plus modifiable")

            image = next((i for i in ticket.images if i.id == image_id), None)
            if image is None:
                raise StorageError("Photo introuvable dans cette session")

            couple = tuple(mesures) if mesures else None
            try:
                montant = catalogue.prix(matiere, format_, forme, orientation, couple, points)
            except catalogue.CatalogueError as exc:
                raise StorageError(str(exc)) from exc

            image.article = Article(
                matiere=matiere, format=format_, forme=forme,
                prix=montant, orientation=orientation,
                mesures=list(couple) if couple else None,
                points=points if forme == catalogue.FORME_LIBRE else None,
            )
            self._save()
            return image

    def mark_paid(self, jeton: str) -> Ticket:
        """Enregistre le reglement d'une commande."""
        with self._lock:
            ticket = self.get_by_payment(jeton)
            if ticket is None:
                raise StorageError("Commande inconnue ou expiree")
            if not ticket.validated:
                raise StorageError("Cette commande n'est pas encore validee sur la borne")
            if not ticket.paid:
                ticket.paid_at = time.time()
                self._save()
            return ticket

    def validate(self, token: str) -> Ticket:
        """Cloture la session : le code de retrait devient utilisable."""
        with self._lock:
            ticket = self.get_by_token(token)
            if ticket is None:
                raise StorageError("Session inconnue ou expiree")
            if not ticket.images:
                raise StorageError("Aucune photo recue pour le moment")
            if not ticket.configured:
                raise StorageError("Chaque photo doit avoir un tirage choisi avant validation")
            if not ticket.validated:
                ticket.validated_at = time.time()
                # Le delai de retrait court a partir de la validation.
                ticket.expires_at = ticket.validated_at + config.RETENTION_HOURS * 3600
                self._save()
            return ticket

    def _new_code(self) -> str:
        span = 10 ** config.CODE_LENGTH
        for _ in range(200):
            code = f"{secrets.randbelow(span):0{config.CODE_LENGTH}d}"
            if code not in self._tickets:
                return code
        raise StorageError("Impossible de generer un code libre, videz les depots")

    def add_image(self, token: str, name: str, mime: str, data: bytes) -> Image:
        if mime not in config.ALLOWED_TYPES:
            raise StorageError(f"Type de fichier non autorise : {mime}")
        if not data:
            raise StorageError("Fichier vide")
        if len(data) > config.MAX_FILE_BYTES:
            limit = config.MAX_FILE_BYTES // (1024 * 1024)
            raise StorageError(f"Fichier trop volumineux (max {limit} Mo)")

        with self._lock:
            ticket = self.get_by_token(token)
            if ticket is None:
                raise StorageError("Session inconnue ou expiree")
            if ticket.validated:
                raise StorageError("Ce depot est deja valide, ouvrez une nouvelle session")
            if len(ticket.images) >= config.MAX_FILES_PER_TICKET:
                raise StorageError(f"Maximum {config.MAX_FILES_PER_TICKET} fichiers par depot")

            image_id = uuid.uuid4().hex
            filename = image_id + config.ALLOWED_TYPES[mime]
            self._assurer_dossier()
            (config.FILES_DIR / filename).write_bytes(data)

            size = imagemeta.dimensions(data)
            image = Image(
                id=image_id,
                name=clean_name(name),
                mime=mime,
                size=len(data),
                filename=filename,
                created_at=time.time(),
                width=size[0] if size else None,
                height=size[1] if size else None,
            )
            ticket.images.append(image)
            self._save()
            return image

    def delete_image(self, image_id: str) -> bool:
        with self._lock:
            found = self.find_image(image_id)
            if found is None:
                return False
            ticket, image = found
            ticket.images.remove(image)
            self._unlink(image)
            self._save()
            return True

    def delete_ticket(self, code: str) -> bool:
        with self._lock:
            ticket = self._tickets.pop(code, None)
            if ticket is None:
                return False
            self._by_token.pop(ticket.token, None)
            self._by_payment.pop(ticket.payment_token, None)
            for image in ticket.images:
                self._unlink(image)
            self._save()
            return True

    def abandon(self, token: str) -> bool:
        """Annule une session en cours depuis la borne."""
        with self._lock:
            ticket = self._by_token.get(token)
            return self.delete_ticket(ticket.code) if ticket else False

    def clear(self) -> int:
        with self._lock:
            count = len(self._tickets)
            for ticket in list(self._tickets.values()):
                for image in ticket.images:
                    self._unlink(image)
            self._tickets.clear()
            self._by_token.clear()
            self._by_payment.clear()
            self._save()
            return count

    def purge(self) -> int:
        """Supprime les depots expires. Retourne le nombre de depots retires."""
        now = time.time()
        limite_brouillon = now - config.DRAFT_RETENTION_HOURS * 3600
        with self._lock:
            expired = [
                code
                for code, ticket in self._tickets.items()
                if ticket.expires_at <= now
                # Une session ouverte puis abandonnee sur la borne ne doit pas
                # encombrer l'index jusqu'a la fin du delai de retrait.
                or (
                    not ticket.validated
                    and not ticket.images
                    and ticket.created_at <= limite_brouillon
                )
            ]
            for code in expired:
                ticket = self._tickets.pop(code)
                self._by_token.pop(ticket.token, None)
                self._by_payment.pop(ticket.payment_token, None)
                for image in ticket.images:
                    self._unlink(image)
            if expired:
                self._save()
            return len(expired)

    def _unlink(self, image: Image) -> None:
        try:
            self.path_of(image).unlink()
        except OSError:
            pass
