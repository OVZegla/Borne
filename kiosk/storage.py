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

from . import config, imagemeta


class StorageError(Exception):
    """Depot invalide ou refuse."""


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

    def public(self) -> dict:
        data = asdict(self)
        data.pop("filename")
        return data


@dataclass
class Ticket:
    code: str
    token: str
    created_at: float
    expires_at: float
    validated_at: float | None = None
    images: list[Image] = field(default_factory=list)

    @property
    def validated(self) -> bool:
        return self.validated_at is not None

    def public(self) -> dict:
        """Vue destinee au poste de retrait : le code y figure."""
        return {
            "code": self.code,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "validated_at": self.validated_at,
            "images": [image.public() for image in self.images],
        }

    def session(self) -> dict:
        """Vue destinee a la borne et au telephone : pas de code avant validation."""
        data = {
            "token": self.token,
            "created_at": self.created_at,
            "validee": self.validated,
            "images": [image.public() for image in self.images],
        }
        if self.validated:
            data["code"] = self.code
        return data


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
        config.FILES_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

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
                images = [Image(**img) for img in entry.get("images", [])]
                ticket = Ticket(
                    code=entry["code"],
                    token=entry["token"],
                    created_at=entry["created_at"],
                    expires_at=entry["expires_at"],
                    validated_at=entry.get("validated_at"),
                    images=images,
                )
            except (KeyError, TypeError):
                continue
            self._tickets[ticket.code] = ticket
            self._by_token[ticket.token] = ticket

    def _save(self) -> None:
        payload = {
            "version": 2,
            "tickets": [
                {
                    "code": t.code,
                    "token": t.token,
                    "created_at": t.created_at,
                    "expires_at": t.expires_at,
                    "validated_at": t.validated_at,
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
        """Ouvre une session : le jeton part dans le QR, le code reste cache."""
        with self._lock:
            self.purge()
            now = time.time()
            ticket = Ticket(
                code=self._new_code(),
                token=secrets.token_urlsafe(9),
                created_at=now,
                expires_at=now + config.RETENTION_HOURS * 3600,
            )
            self._tickets[ticket.code] = ticket
            self._by_token[ticket.token] = ticket
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
