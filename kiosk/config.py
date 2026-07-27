"""Configuration du Symp's Kiosk, surchargeable par variables d'environnement."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


HOST = os.environ.get("SYMPS_HOST", "0.0.0.0")
PORT = _int_env("SYMPS_PORT", 8080)

DATA_DIR = Path(os.environ.get("SYMPS_DATA", BASE_DIR / "depots")).resolve()
FILES_DIR = DATA_DIR / "fichiers"
INDEX_FILE = DATA_DIR / "index.json"

# Duree de vie d'un depot avant suppression automatique.
RETENTION_HOURS = _int_env("SYMPS_RETENTION_HOURS", 24)

MAX_FILE_BYTES = _int_env("SYMPS_MAX_MB", 25) * 1024 * 1024
MAX_FILES_PER_TICKET = _int_env("SYMPS_MAX_FILES", 20)

CODE_LENGTH = 4

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "application/pdf": ".pdf",
}

BRAND_NAME = "Symp's Kiosk"
BRAND_COLOR = "#00287E"
