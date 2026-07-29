"""Serveur HTTP du Symp's Kiosk (bibliotheque standard uniquement)."""

from __future__ import annotations

import io
import json
import mimetypes
import os
import queue
import socket
import threading
import time
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import catalogue, config, qr, reseau
from .storage import Store, StorageError

STORE = Store()


# --- diffusion temps reel vers les pages ouvertes ------------------------------


class Broker:
    """Bus publication/abonnement pour les flux SSE.

    Deux canaux : le canal public (poste de retrait) et un canal par session,
    pour que le jeton d'une borne ne fuite pas vers les autres pages ouvertes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[tuple[str | None, queue.Queue]] = set()

    def subscribe(self, canal: str | None = None) -> tuple[str | None, queue.Queue]:
        abonne = (canal, queue.Queue(maxsize=64))
        with self._lock:
            self._subscribers.add(abonne)
        return abonne

    def unsubscribe(self, abonne: tuple[str | None, queue.Queue]) -> None:
        with self._lock:
            self._subscribers.discard(abonne)

    def publish(self, event: str, data: dict, canal: str | None = None) -> None:
        message = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self._lock:
            targets = [channel for abonne, channel in self._subscribers if abonne == canal]
        for channel in targets:
            try:
                channel.put_nowait(message)
            except queue.Full:
                pass


BROKER = Broker()


# --- utilitaires reseau --------------------------------------------------------


def local_addresses() -> list[str]:
    """Adresses IPv4 sur lesquelles la borne est joignable depuis le reseau."""
    found: list[str] = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.168.255.255", 1))
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found and not address.startswith("127."):
                found.append(address)
    except OSError:
        pass
    return found


def base_urls(port: int) -> list[str]:
    urls = [f"http://localhost:{port}"]
    urls += [f"http://{address}:{port}" for address in local_addresses()]
    return urls


def preferred_url(port: int) -> str:
    """L'URL a afficher aux autres appareils (IP du reseau si disponible)."""
    addresses = local_addresses()
    host = addresses[0] if addresses else "localhost"
    return f"http://{host}:{port}"


# --- serveur -------------------------------------------------------------------


class KioskServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = config.port_reutilisable()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SympsKiosk"
    sys_version = ""

    # --- reponses ---------------------------------------------------------

    def _send(
        self,
        status: HTTPStatus | int,
        body: bytes = b"",
        content_type: str = "text/plain; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(self, payload, status: HTTPStatus | int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: HTTPStatus | int, message: str) -> None:
        self._json({"erreur": message}, status)

    def _redirect(self, location: str) -> None:
        self._send(HTTPStatus.SEE_OTHER, b"", headers={"Location": location})

    def log_message(self, fmt: str, *args) -> None:  # moins bavard que le defaut
        if os.environ.get("SYMPS_VERBOSE"):
            super().log_message(fmt, *args)

    # --- routage ----------------------------------------------------------

    def do_GET(self) -> None:
        self._route("GET")

    def do_HEAD(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_DELETE(self) -> None:
        self._route("DELETE")

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            self._dispatch(method, path, query)
        except StorageError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # pragma: no cover - filet de securite
            self.log_error("erreur interne: %r", exc)
            try:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Erreur interne du serveur")
            except OSError:
                pass

    def _dispatch(self, method: str, path: str, query: dict) -> None:
        pages = {
            "/": "index.html",
            "/envoyer": "envoyer.html",
            "/paiement": "paiement.html",
            "/recuperer": "recuperer.html",
            "/impression": "impression.html",
        }

        if method == "GET":
            if path in pages:
                return self._serve_file(config.WEB_DIR / pages[path])
            if path.startswith("/assets/"):
                return self._serve_asset(path)
            if path == "/e":  # lien court encode dans le QR code de la borne
                token = (query.get("s") or [""])[0]
                return self._redirect(f"/envoyer?s={quote(token)}")
            if path == "/p":  # lien court du QR code de paiement
                jeton = (query.get("j") or [""])[0]
                return self._redirect(f"/paiement?j={quote(jeton)}")
            if path == "/r":  # lien court vers un depot deja valide
                code = (query.get("c") or [""])[0]
                return self._redirect(f"/recuperer?code={quote(code)}")
            if path == "/qr.svg":
                return self._qr(query)
            if path == "/api/config":
                return self._config()
            if path == "/api/catalogue":
                return self._json(catalogue.public())
            if path.startswith("/api/paiement/"):
                return self._get_payment(path[len("/api/paiement/"):])
            if path == "/api/depots":
                return self._json([t.public() for t in STORE.recent()])
            if path == "/api/evenements":
                return self._events((query.get("session") or [None])[0])
            if path.startswith("/api/sessions/"):
                return self._get_session(path[len("/api/sessions/"):])
            if path.startswith("/api/depots/"):
                return self._get_ticket(path)
            if path.startswith("/media/"):
                return self._media(path.split("/media/", 1)[1], "dl" in query)

        elif method == "POST":
            if path == "/api/sessions":
                return self._open_session()
            if path.startswith("/api/sessions/") and path.endswith("/images"):
                token = path[len("/api/sessions/"):-len("/images")]
                return self._upload(token)
            if path.startswith("/api/sessions/") and path.endswith("/valider"):
                token = path[len("/api/sessions/"):-len("/valider")]
                return self._validate(token)
            if path.startswith("/api/sessions/") and "/images/" in path:
                reste = path[len("/api/sessions/"):]
                token, _, fin = reste.partition("/images/")
                if fin.endswith("/article"):
                    return self._set_article(token, fin[: -len("/article")])
            if path.startswith("/api/paiement/") and path.endswith("/regler"):
                return self._pay(path[len("/api/paiement/"):-len("/regler")])

        elif method == "DELETE":
            if path == "/api/depots":
                removed = STORE.clear()
                BROKER.publish("purge", {"depots": removed})
                return self._json({"supprimes": removed})
            if path.startswith("/api/sessions/"):
                token = path[len("/api/sessions/"):]
                if not STORE.abandon(token):
                    return self._error(HTTPStatus.NOT_FOUND, "Session introuvable")
                return self._json({"abandonnee": True})
            if path.startswith("/api/depots/"):
                code = path[len("/api/depots/"):]
                if not STORE.delete_ticket(code):
                    return self._error(HTTPStatus.NOT_FOUND, "Depot introuvable")
                BROKER.publish("suppression", {"code": code})
                return self._json({"supprime": code})
            if path.startswith("/api/images/"):
                image_id = path[len("/api/images/"):]
                return self._delete_image(image_id)

        self._error(HTTPStatus.NOT_FOUND, "Ressource introuvable")

    # --- gestionnaires ----------------------------------------------------

    def _config(self) -> None:
        port = self.server.server_address[1]
        self._json(
            {
                "marque": config.BRAND_NAME,
                "couleur": config.BRAND_COLOR,
                "urls": base_urls(port),
                "url_reseau": preferred_url(port),
                "retention_heures": config.RETENTION_HOURS,
                "taille_max_mo": config.MAX_FILE_BYTES // (1024 * 1024),
                "fichiers_max": config.MAX_FILES_PER_TICKET,
                "types_autorises": sorted(config.ALLOWED_TYPES),
            }
        )

    def _open_session(self) -> None:
        """La borne ouvre une session et recoit le lien a mettre dans son QR code."""
        ticket = STORE.create_ticket()
        port = self.server.server_address[1]
        payload = ticket.session()
        payload["url_envoi"] = f"{preferred_url(port)}/e?s={ticket.token}"
        self._json(payload, HTTPStatus.CREATED)

    def _get_session(self, token: str) -> None:
        ticket = STORE.get_by_token(token)
        if ticket is None:
            return self._error(HTTPStatus.NOT_FOUND, "Session inconnue ou expiree")
        self._json(ticket.session())

    def _set_article(self, token: str, image_id: str) -> None:
        """Choix du tirage pour une photo : matiere, format, forme."""
        choix = self._read_json()
        if choix is None:
            return self._error(HTTPStatus.BAD_REQUEST, "Corps JSON attendu")
        image = STORE.set_article(
            token,
            image_id,
            str(choix.get("matiere", "")),
            str(choix.get("format", "")),
            str(choix.get("forme", "initial")),
        )
        BROKER.publish("article", {"image": image.public()}, canal=token)
        self._json(image.public())

    def _validate(self, token: str) -> None:
        """L'operateur valide sur la borne : le code de retrait est revele."""
        ticket = STORE.validate(token)
        port = self.server.server_address[1]
        payload = ticket.session()
        payload["url_paiement"] = f"{preferred_url(port)}/p?j={ticket.payment_token}"
        BROKER.publish("depot", ticket.public())  # le poste de reception rafraichit sa liste
        BROKER.publish("validation", payload, canal=token)
        self._json(payload)

    def _get_payment(self, jeton: str) -> None:
        ticket = STORE.get_by_payment(jeton)
        if ticket is None or not ticket.validated:
            return self._error(HTTPStatus.NOT_FOUND, "Commande inconnue ou expiree")
        self._json(ticket.paiement())

    def _pay(self, jeton: str) -> None:
        """Enregistre le reglement.

        Aucun prestataire de paiement n'est branche : cette route se contente de
        marquer la commande comme reglee. C'est ici qu'un encaissement reel
        (Stripe, SumUp...) viendrait se greffer, apres verification cote serveur.
        """
        ticket = STORE.mark_paid(jeton)
        BROKER.publish("paiement", ticket.public())  # poste de reception
        BROKER.publish("paiement", ticket.session(), canal=ticket.token)  # la borne
        BROKER.publish("paiement", ticket.paiement(), canal=jeton)  # page de reglement
        self._json(ticket.paiement())

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64 * 1024:
            return None
        brut = self._read_exactly(length)
        if brut is None:
            return None
        try:
            charge = json.loads(brut.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return charge if isinstance(charge, dict) else None

    def _delete_image(self, image_id: str) -> None:
        found = STORE.find_image(image_id)
        if found is None:
            return self._error(HTTPStatus.NOT_FOUND, "Image introuvable")
        ticket = found[0]
        canal = None if ticket.validated else ticket.token
        if not STORE.delete_image(image_id):
            return self._error(HTTPStatus.NOT_FOUND, "Image introuvable")
        BROKER.publish("suppression", {"image": image_id}, canal=canal)
        self._json({"supprime": image_id})

    def _get_ticket(self, path: str) -> None:
        rest = path[len("/api/depots/"):]
        if rest.endswith("/zip"):
            return self._zip(rest[: -len("/zip")])
        ticket = STORE.get(rest)
        if ticket is None:
            return self._error(HTTPStatus.NOT_FOUND, "Aucun depot avec ce code")
        self._json(ticket.public())

    def _upload(self, token: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._error(HTTPStatus.BAD_REQUEST, "Requete sans contenu")
        if length > config.MAX_FILE_BYTES:
            # Le client est deja en train d'envoyer : on absorbe son flux, sinon il
            # recoit une connexion coupee au lieu du message d'erreur.
            self._drain(length)
            self.close_connection = True
            limit = config.MAX_FILE_BYTES // (1024 * 1024)
            return self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"Fichier trop volumineux (max {limit} Mo)"
            )

        data = self._read_exactly(length)
        if data is None:
            return self._error(HTTPStatus.BAD_REQUEST, "Transfert interrompu")

        mime = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        name = unquote(self.headers.get("X-Nom-Fichier") or "")
        image = STORE.add_image(token, name, mime, data)
        # Seule la borne de cette session est notifiee : c'est elle qui affiche
        # la photo en grand des sa reception.
        BROKER.publish("image", {"image": image.public()}, canal=token)
        self._json(image.public(), HTTPStatus.CREATED)

    def _drain(self, length: int, plafond: int = 512 * 1024 * 1024) -> None:
        """Lit et jette le corps de la requete, pour pouvoir repondre proprement."""
        remaining = min(length, plafond)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 256 * 1024))
            if not chunk:
                return
            remaining -= len(chunk)

    def _read_exactly(self, length: int) -> bytes | None:
        chunks = []
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 64 * 1024))
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _media(self, image_id: str, download: bool) -> None:
        found = STORE.find_image(image_id)
        if found is None:
            return self._error(HTTPStatus.NOT_FOUND, "Image introuvable")
        _, image = found
        path = STORE.path_of(image)
        try:
            data = path.read_bytes()
        except OSError:
            return self._error(HTTPStatus.NOT_FOUND, "Fichier absent du disque")

        disposition = "attachment" if download else "inline"
        self._send(
            HTTPStatus.OK,
            data,
            image.mime,
            {"Content-Disposition": f'{disposition}; filename*=UTF-8\'\'{quote(image.name)}'},
        )

    def _zip(self, code: str) -> None:
        ticket = STORE.get(code)
        if ticket is None:
            return self._error(HTTPStatus.NOT_FOUND, "Aucun depot avec ce code")
        if not ticket.images:
            return self._error(HTTPStatus.NOT_FOUND, "Ce depot ne contient aucune image")

        buffer = io.BytesIO()
        used: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, image in enumerate(ticket.images, start=1):
                name = image.name
                if name in used:
                    stem, dot, ext = name.rpartition(".")
                    name = f"{stem or name}-{index}{dot}{ext}" if dot else f"{name}-{index}"
                used.add(name)
                try:
                    archive.write(STORE.path_of(image), name)
                except OSError:
                    continue

        self._send(
            HTTPStatus.OK,
            buffer.getvalue(),
            "application/zip",
            {"Content-Disposition": f'attachment; filename="symps-kiosk-{code}.zip"'},
        )

    def _qr(self, query: dict) -> None:
        data = (query.get("d") or [""])[0]
        if not data:
            return self._error(HTTPStatus.BAD_REQUEST, "Parametre 'd' manquant")
        try:
            svg = qr.to_svg(data, dark=config.BRAND_COLOR)
        except qr.QRError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        self._send(HTTPStatus.OK, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")

    def _events(self, canal: str | None = None) -> None:
        abonne = BROKER.subscribe(canal)
        channel = abonne[1]
        self.close_connection = True
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b": connecte\n\n")
            self.wfile.flush()
            while True:
                try:
                    message = channel.get(timeout=20)
                except queue.Empty:
                    message = ": ping\n\n"
                self.wfile.write(message.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            BROKER.unsubscribe(abonne)

    # --- fichiers statiques ------------------------------------------------

    def _serve_asset(self, path: str) -> None:
        relative = path[len("/assets/"):]
        target = (config.WEB_DIR / "assets" / relative).resolve()
        assets_root = (config.WEB_DIR / "assets").resolve()
        if not str(target).startswith(str(assets_root) + os.sep):
            return self._error(HTTPStatus.FORBIDDEN, "Chemin refuse")
        self._serve_file(target)

    def _serve_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            return self._error(HTTPStatus.NOT_FOUND, "Fichier introuvable")
        guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if guessed.startswith("text/") or guessed in ("application/javascript", "image/svg+xml"):
            guessed += "; charset=utf-8"
        self._send(HTTPStatus.OK, data, guessed)


# --- demarrage -----------------------------------------------------------------


def _purge_loop() -> None:
    while True:
        time.sleep(300)
        try:
            if STORE.purge():
                BROKER.publish("purge", {"auto": True})
        except Exception:  # pragma: no cover - le nettoyage ne doit jamais tuer le thread
            pass


def build_server(host: str, port: int, attempts: int = 20) -> KioskServer:
    """Ouvre le serveur, en glissant sur le port suivant s'il est deja pris."""
    last: OSError | None = None
    for offset in range(attempts):
        try:
            return KioskServer((host, port + offset), Handler)
        except OSError as exc:
            last = exc
    raise SystemExit(f"Aucun port libre entre {port} et {port + attempts - 1} ({last})")


def serve(
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = False,
    atelier: str | None = None,
) -> None:
    server = build_server(host or config.HOST, port or config.PORT)
    actual_port = server.server_address[1]

    threading.Thread(target=_purge_loop, daemon=True).start()

    # Les autres machines de la boutique trouveront cet hote toutes seules.
    annonceur = reseau.Annonceur(atelier or config.atelier(), actual_port)
    annonceur.demarrer()

    if open_browser:
        import webbrowser

        threading.Timer(0.8, webbrowser.open, [f"http://localhost:{actual_port}"]).start()

    print(f"\n  {config.BRAND_NAME} - cette machine est l'hote.\n")
    print(f"  Sur cette machine   : http://localhost:{actual_port}")
    for address in local_addresses():
        print(f"  Depuis un autre app.: http://{address}:{actual_port}")
    print("\n  Les autres postes de la boutique s'y connecteront tout seuls.")
    print(f"\n  Depots conserves {config.RETENTION_HOURS} h dans {config.DATA_DIR}")
    print("  Ctrl+C pour arreter.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arret du Symp's Kiosk.")
    finally:
        annonceur.arreter()
        server.shutdown()
        server.server_close()
