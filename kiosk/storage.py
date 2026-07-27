"""Stockage des depots : un depot = un code a 4 chiffres + ses images."""

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
    created_at: float
    expires_at: float
    images: list[Image] = field(default_factory=list)

    def public(self) -> dict:
        return {
            "code": self.code,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "images": [image.public() for image in self.images],
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
                    created_at=entry["created_at"],
                    expires_at=entry["expires_at"],
                    images=images,
                )
            except (KeyError, TypeError):
                continue
            self._tickets[ticket.code] = ticket

    def _save(self) -> None:
        payload = {
            "version": 1,
            "tickets": [
                {
                    "code": t.code,
                    "created_at": t.created_at,
                    "expires_at": t.expires_at,
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
        with self._lock:
            self.purge()
            return self._tickets.get(code)

    def recent(self, limit: int = 30) -> list[Ticket]:
        with self._lock:
            self.purge()
            tickets = sorted(self._tickets.values(), key=lambda t: t.created_at, reverse=True)
            return tickets[:limit]

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
        with self._lock:
            self.purge()
            now = time.time()
            ticket = Ticket(
                code=self._new_code(),
                created_at=now,
                expires_at=now + config.RETENTION_HOURS * 3600,
            )
            self._tickets[ticket.code] = ticket
            self._save()
            return ticket

    def _new_code(self) -> str:
        span = 10 ** config.CODE_LENGTH
        for _ in range(200):
            code = f"{secrets.randbelow(span):0{config.CODE_LENGTH}d}"
            if code not in self._tickets:
                return code
        raise StorageError("Impossible de generer un code libre, videz les depots")

    def add_image(self, code: str, name: str, mime: str, data: bytes) -> Image:
        if mime not in config.ALLOWED_TYPES:
            raise StorageError(f"Type de fichier non autorise : {mime}")
        if not data:
            raise StorageError("Fichier vide")
        if len(data) > config.MAX_FILE_BYTES:
            limit = config.MAX_FILE_BYTES // (1024 * 1024)
            raise StorageError(f"Fichier trop volumineux (max {limit} Mo)")

        with self._lock:
            ticket = self._tickets.get(code)
            if ticket is None:
                raise StorageError("Depot inconnu ou expire")
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
            for image in ticket.images:
                self._unlink(image)
            self._save()
            return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._tickets)
            for ticket in list(self._tickets.values()):
                for image in ticket.images:
                    self._unlink(image)
            self._tickets.clear()
            self._save()
            return count

    def purge(self) -> int:
        """Supprime les depots expires. Retourne le nombre de depots retires."""
        now = time.time()
        with self._lock:
            expired = [c for c, t in self._tickets.items() if t.expires_at <= now]
            for code in expired:
                ticket = self._tickets.pop(code)
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
