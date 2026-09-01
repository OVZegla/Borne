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

from . import catalogue, config, licence, postes, qr, reglages, reseau, tableau, tunnel
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

# Port de la porte publique une fois ouverte, ou None.
PORTE_PUBLIQUE: int | None = None

# La page des reglages suit l'ouverture du tunnel en direct, sans rafraichir.
tunnel.TUNNEL.observer(lambda etat: BROKER.publish("tunnel", etat))


def appliquer_acces_distant() -> dict:
    """Aligne le tunnel sur le reglage courant : demarre, arrete, ou rien.

    Appele au demarrage et apres chaque enregistrement des reglages, pour que
    l'interrupteur de la page agisse tout de suite.
    """
    mode = reglages.tout()["acces_distant"].get("mode")
    if mode == "auto" and PORTE_PUBLIQUE:
        return tunnel.TUNNEL.demarrer(PORTE_PUBLIQUE)
    return tunnel.TUNNEL.arreter()


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


def lien_client(port: int) -> str:
    """Adresse a encoder dans les QR codes tendus au telephone du client.

    Celle du tunnel quand la boutique a declare une adresse publique, sinon
    celle du reseau local — qui n'est joignable que depuis le Wi-Fi du magasin.
    """
    return reglages.url_publique() or preferred_url(port)


def _jeton_de(path: str, prefixe: str) -> str | None:
    """Jeton d'une route `<prefixe><jeton>`, sans suffixe ni sous-chemin."""
    if not path.startswith(prefixe):
        return None
    reste = path[len(prefixe):]
    return reste if reste and "/" not in reste else None


def _melanger(couleur: str, vers: int, part: float) -> str:
    """Rapproche une couleur du noir ou du blanc, pour deriver une palette."""
    couleur = couleur.lstrip("#")
    canaux = [int(couleur[i:i + 2], 16) for i in (0, 2, 4)]
    melange = [round(c + (vers - c) * part) for c in canaux]
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in melange)


def _assombrir(couleur: str, facteur: float) -> str:
    """facteur < 1 assombrit, facteur > 1 eclaircit legerement."""
    if facteur <= 1:
        return _melanger(couleur, 0, 1 - facteur)
    return _melanger(couleur, 255, min(1.0, facteur - 1))


def _eclaircir(couleur: str, part: float) -> str:
    return _melanger(couleur, 255, part)


def clarte(couleur: str) -> float:
    """Luminosite percue d'une couleur, entre 0 (noir) et 1 (blanc).

    Ponderation ITU-R BT.601 : l'oeil voit le vert bien plus que le bleu.
    Elle decide si le texte doit etre sombre ou clair sur ce fond, pour qu'une
    boutique puisse choisir un fond noir sans rendre ses pages illisibles.
    """
    couleur = couleur.lstrip("#")
    r, v, b = (int(couleur[i:i + 2], 16) for i in (0, 2, 4))
    return (r * 299 + v * 587 + b * 114) / 255000


def feuille_theme(theme: dict) -> str:
    """Palette complete deduite des trois couleurs choisies par la boutique.

    Le fond decide du reste : sur un fond clair les surfaces sont blanches et
    le texte sombre, sur un fond sombre c'est l'inverse. La boutique choisit
    donc librement ses couleurs sans jamais fabriquer une page illisible.
    """
    primaire = theme["primaire"]
    accent = theme["accent"]
    fond = theme.get("fond") or "#F2F6FD"
    sombre = clarte(fond) < 0.5

    if sombre:
        surface = _eclaircir(fond, 0.10)
        encre = "#f4f7ff"
        gris = _melanger(fond, 255, 0.62)
        bordure = _eclaircir(fond, 0.20)
        # Sur fond sombre, la couleur principale doit s'eclaircir pour rester
        # lisible : un bleu nuit sur du noir ne se voit plus.
        primaire = _eclaircir(primaire, 0.30)
        accent = _eclaircir(accent, 0.20)
        halo = _melanger(fond, 255, 0.14)
    else:
        surface = "#ffffff"
        encre = _assombrir(primaire, 0.16)
        gris = _melanger(_assombrir(primaire, 0.45), 255, 0.42)
        bordure = _eclaircir(accent, 0.82)
        halo = _eclaircir(accent, 0.80)

    # Texte pose sur la couleur principale : blanc si elle est sombre, sinon
    # une version tres foncee d'elle-meme. Sans cela, un theme clair affiche du
    # blanc sur du pastel, illisible.
    sur_primaire = "#ffffff" if clarte(primaire) < 0.6 else _assombrir(primaire, 0.18)

    return (
        ":root{\n"
        f"  --sur-primaire: {sur_primaire};\n"
        # En mode nuit, la signature Symp's passe en blanc sur fond transparent :
        # `brightness(0)` la rend noire, `invert(1)` la retourne en blanc, et les
        # pixels transparents le restent.
        f"  --marque-filtre: {'brightness(0) invert(1)' if sombre else 'none'};\n"
        # Le logo de la boutique, lui, reste tel qu'elle l'a fourni : on lui pose
        # seulement une plaque claire si le fond est sombre.
        f"  --logo-fond: {'#ffffff' if sombre else 'transparent'};\n"
        f"  --logo-cadre: {'0.3rem 0.5rem' if sombre else '0'};\n"
        f"  --bleu-800: {primaire};\n"
        f"  --bleu-900: {_assombrir(primaire, 0.72) if not sombre else _eclaircir(primaire, 0.30)};\n"
        f"  --bleu-700: {_assombrir(primaire, 1.22)};\n"
        f"  --bleu-600: {accent};\n"
        f"  --bleu-500: {_eclaircir(accent, 0.25)};\n"
        f"  --bleu-200: {_melanger(accent, 255 if not sombre else 0, 0.62)};\n"
        f"  --bleu-100: {_melanger(accent, 255 if not sombre else 0, 0.80)};\n"
        f"  --bleu-050: {_melanger(accent, 255 if not sombre else 0, 0.93)};\n"
        f"  --fond: {fond};\n"
        f"  --halo: {halo};\n"
        f"  --surface: {surface};\n"
        f"  --encre: {encre};\n"
        f"  --gris: {gris};\n"
        f"  --bordure: {bordure};\n"
        "}\n"
    )


# --- serveur -------------------------------------------------------------------


class KioskServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = config.port_reutilisable()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SympsKiosk"
    sys_version = ""

    # Vrai sur la porte ou se branche le tunnel. Voir PublicHandler, en bas.
    PUBLIC = False

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
        # Les jetons de depot et de reglement voyagent dans l'URL : aucun
        # referent ne doit partir avec, en particulier vers la page de paiement
        # externe de la boutique, qui reçoit sinon le jeton de la commande.
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(
        self,
        payload,
        status: HTTPStatus | int = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", headers)

    def _error(self, status: HTTPStatus | int, message: str) -> None:
        self._json({"erreur": message}, status)

    def _redirect(self, location: str) -> None:
        self._send(HTTPStatus.SEE_OTHER, b"", headers={"Location": location})

    # --- identite de l'appareil -------------------------------------------

    def _cookie(self, nom: str) -> str | None:
        """Lit un cookie sans dependance : l'en-tete est une liste `a=b; c=d`."""
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            cle, _, valeur = morceau.strip().partition("=")
            if cle == nom:
                return unquote(valeur)
        return None

    def _jeton_poste(self) -> str | None:
        return self._cookie(postes.COOKIE)

    def _poser_cookie_poste(self, jeton: str) -> dict[str, str]:
        # Pas de `Secure` : la boutique tourne en HTTP sur son reseau local, et
        # un cookie `Secure` n'y serait jamais renvoye.
        return {
            "Set-Cookie": f"{postes.COOKIE}={quote(jeton)}; Path=/; Max-Age=31536000; "
                          "HttpOnly; SameSite=Lax"
        }

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

    # Accessibles sans abonnement actif : de quoi se connecter, et rien d'autre.
    LIBRES = ("/connexion", "/api/compte", "/api/config", "/assets/")

    def _abonnement_bloque(self, path: str) -> bool:
        if any(path == libre or path.startswith(libre) for libre in self.LIBRES):
            return False
        return not licence.etat_actuel().get("utilisable", True)

    PAGES = {
        "/": ("index.html", "borne"),
        "/connexion": ("connexion.html", None),
        "/reglages": ("reglages.html", "reglages"),
        "/tableau": ("tableau.html", "tableau"),
        "/recuperer": ("recuperer.html", "reception"),
        "/impression": ("impression.html", "impression"),
        # Pages ouvertes depuis le telephone du client : aucun role, le secret
        # est le jeton contenu dans le QR code.
        "/envoyer": ("envoyer.html", None),
        "/paiement": ("paiement.html", None),
    }

    def _droit_requis(self, method: str, path: str) -> str | None:
        """Droit exige par une route, ou None si elle est ouverte a tous.

        Restent ouvertes les routes que le telephone d'un client doit atteindre :
        il n'est pas un poste de la boutique et n'a pas de role.
        """
        if path in self.PAGES:
            return self.PAGES[path][1]

        if path.startswith("/api/sessions"):
            # Consulter une session ou y deposer une photo : le telephone le fait.
            if method == "GET" and not path.endswith("/code"):
                return None
            if method == "POST" and path.endswith("/images"):
                return None
            return "borne"

        if path.startswith("/api/reglages") or path == "/api/tunnel":
            return "reglages"
        if path == "/api/tableau":
            return "tableau"
        if path.startswith("/api/depots") or path.startswith("/api/images/") or path == "/r":
            return "reception"
        return None

    def _role_bloque(self, method: str, path: str) -> str | None:
        """Renvoie le droit manquant, ou None si l'appareil peut continuer."""
        droit = self._droit_requis(method, path)
        if droit is None:
            return None
        return None if postes.a_le_droit(self._jeton_poste(), droit) else droit

    # --- surface exposee au bout du tunnel --------------------------------

    # Ce que le telephone d'un client atteint depuis Internet, et rien d'autre.
    # C'est une liste blanche, et c'est le point : une route ajoutee au serveur
    # n'apparait ici que si on l'y met. L'oubli ferme la porte, il ne l'ouvre
    # pas — l'inverse aurait mis la reception en ligne au premier ajout.
    SURFACE_PUBLIQUE = {
        "/envoyer",         # page d'envoi des photos
        "/paiement",        # page de reglement
        "/e",               # lien court du QR code de depot
        "/p",               # lien court du QR code de paiement
        "/api/config",      # marque, limites de taille, types acceptes
        "/api/catalogue",   # libelles des tirages, pour le recapitulatif
        "/logo-boutique",
        "/assets/theme.css",
    }

    def _dans_la_surface_publique(self, method: str, path: str, query: dict) -> bool:
        if method == "GET":
            if path in self.SURFACE_PUBLIQUE or path.startswith("/assets/"):
                return True
            # Suivi en direct d'une commande. Le jeton est obligatoire : sans
            # lui l'abonnement porte sur le canal general de la boutique, qui
            # diffuse chaque depot valide — ceux des autres clients compris.
            if path == "/api/evenements":
                return bool((query.get("session") or [""])[0])
            if _jeton_de(path, "/api/paiement/") is not None:
                return True
            # Consulter sa session, mais pas /code : le code de retrait se
            # revele sur la borne, pas sur le telephone.
            return _jeton_de(path, "/api/sessions/") is not None

        if method == "POST":
            # Deposer une photo, et c'est tout : ni ouverture de session, ni
            # validation, ni choix du tirage. Cela se fait devant la borne.
            reste = path[len("/api/sessions/"):] if path.startswith("/api/sessions/") else ""
            jeton, _, fin = reste.partition("/")
            return bool(jeton) and fin == "images"

        return False

    def _dispatch(self, method: str, path: str, query: dict) -> None:
        pages = {chemin: fichier for chemin, (fichier, _) in self.PAGES.items()}

        if self.PUBLIC and not self._dans_la_surface_publique(method, path, query):
            # 404 plutot que 403 : depuis Internet, rien ne doit laisser
            # deviner qu'il existe une reception, un tableau de bord et des
            # reglages derriere cette adresse.
            return self._error(HTTPStatus.NOT_FOUND, "Ressource introuvable")

        if self._abonnement_bloque(path):
            if self.PUBLIC:
                # Un client n'a rien a savoir de l'abonnement de la boutique.
                return self._error(
                    HTTPStatus.SERVICE_UNAVAILABLE, "Dépôt momentanément indisponible"
                )
            if path in pages or path == "/":
                return self._redirect("/connexion")
            return self._error(HTTPStatus.PAYMENT_REQUIRED, "Abonnement requis")

        if method == "POST" and path == "/api/poste":
            return self._inscrire_poste()
        if method == "GET" and path == "/api/poste":
            return self._json(postes.etat(self._jeton_poste()))
        if method == "DELETE" and path == "/api/poste":
            postes.oublier(self._jeton_poste())
            return self._json({"oublie": True})

        if self._role_bloque(method, path) is not None:
            jeton = self._jeton_poste()
            if path in pages:
                # Un appareil sans role va choisir le sien ; un appareil qui a
                # deja un role revient chez lui plutot que sur un refus sec.
                return self._redirect(postes.accueil(jeton) if jeton else "/connexion")
            return self._error(HTTPStatus.FORBIDDEN, "Ce poste n'a pas accès à cette page")
        postes.vu(self._jeton_poste())

        if method == "POST":
            if path == "/api/compte/connexion":
                return self._connexion()
            if path == "/api/compte/deconnexion":
                licence.oublier()
                return self._json({"deconnecte": True})
        if method == "GET" and path == "/api/compte":
            return self._json(licence.etat_actuel())

        if method == "GET":
            if path in pages:
                return self._serve_file(config.WEB_DIR / pages[path])
            if path == "/assets/theme.css":  # feuille generee, avant les fichiers
                return self._theme()
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
            if path == "/api/tableau":
                return self._json(tableau.resume(STORE))
            if path == "/api/reglages":
                return self._json({**reglages.tout(), "geometries": reglages.GEOMETRIES})
            if path == "/api/tunnel":
                return self._json(self._etat_distant())
            if path == "/logo-boutique":
                return self._logo_boutique()
            if path.startswith("/api/paiement/"):
                return self._get_payment(path[len("/api/paiement/"):])
            if path == "/api/depots":
                return self._json([t.public() for t in STORE.recent()])
            if path == "/api/evenements":
                return self._events((query.get("session") or [None])[0])
            if path.startswith("/api/sessions/") and path.endswith("/code"):
                return self._reveler_code(path[len("/api/sessions/"):-len("/code")])
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
            if path.startswith("/api/depots/") and path.endswith("/paiement"):
                return self._pay(path[len("/api/depots/"):-len("/paiement")])
            if path == "/api/reglages":
                return self._enregistrer_reglages()
            if path == "/api/reglages/logo":
                return self._televerser_logo()

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
            if path == "/api/reglages":
                valeurs = reglages.reinitialiser()
                appliquer_acces_distant()
                BROKER.publish("reglages", {"maj": True})
                return self._json(valeurs)
            if path == "/api/reglages/logo":
                return self._supprimer_logo()
            if path.startswith("/api/images/"):
                image_id = path[len("/api/images/"):]
                return self._delete_image(image_id)

        self._error(HTTPStatus.NOT_FOUND, "Ressource introuvable")

    # --- gestionnaires ----------------------------------------------------

    def _config(self) -> None:
        port = self.server.server_address[1]
        valeurs = reglages.tout()
        payload = {
            "marque": config.BRAND_NAME,
            "version": config.VERSION,
            "boutique": valeurs["boutique"],
            "theme": valeurs["theme"],
            "couleur": config.BRAND_COLOR,
            "retention_heures": config.RETENTION_HOURS,
            "taille_max_mo": config.MAX_FILE_BYTES // (1024 * 1024),
            "fichiers_max": config.MAX_FILES_PER_TICKET,
            "types_autorises": sorted(config.ALLOWED_TYPES),
            "paiement": {"ordre": valeurs["paiement"].get("ordre", "apres")},
        }
        if not self.PUBLIC:
            # Adresses internes de la boutique et role de l'appareil : cela
            # regarde les postes du magasin, pas un telephone venu d'Internet.
            payload.update(
                {
                    "urls": base_urls(port),
                    "url_reseau": preferred_url(port),
                    "url_client": lien_client(port),
                    "acces_distant": valeurs["acces_distant"],
                    "poste": postes.etat(self._jeton_poste()),
                }
            )
        self._json(payload)

    # --- personnalisation de la boutique ----------------------------------

    def _theme(self) -> None:
        """Feuille de style generee : les couleurs choisies par la boutique."""
        self._send(
            HTTPStatus.OK,
            feuille_theme(reglages.tout()["theme"]).encode("utf-8"),
            "text/css; charset=utf-8",
        )

    def _logo_boutique(self) -> None:
        nom = reglages.tout()["boutique"].get("logo")
        if not nom:
            return self._error(HTTPStatus.NOT_FOUND, "Aucun logo de boutique")
        chemin = (config.DATA_DIR / "marque" / nom).resolve()
        racine = (config.DATA_DIR / "marque").resolve()
        if not str(chemin).startswith(str(racine) + os.sep):
            return self._error(HTTPStatus.FORBIDDEN, "Chemin refuse")
        try:
            donnees = chemin.read_bytes()
        except OSError:
            return self._error(HTTPStatus.NOT_FOUND, "Logo introuvable")
        type_mime = mimetypes.guess_type(nom)[0] or "image/png"
        self._send(HTTPStatus.OK, donnees, type_mime)

    def _etat_distant(self) -> dict:
        """Ce que la page des reglages montre du depot a distance."""
        etat = dict(tunnel.TUNNEL.etat())
        etat["mode"] = reglages.tout()["acces_distant"].get("mode", "aucun")
        etat["porte"] = PORTE_PUBLIQUE
        # L'adresse reellement encodee dans les prochains QR codes : c'est elle
        # qui dit si le depot a distance marche pour de bon, pas le reglage.
        etat["url_qr"] = lien_client(self.server.server_address[1])
        etat["distant"] = bool(reglages.url_publique())
        return etat

    def _enregistrer_reglages(self) -> None:
        recu = self._read_json()
        if recu is None:
            return self._error(HTTPStatus.BAD_REQUEST, "Corps JSON attendu")
        try:
            valeurs = reglages.enregistrer(recu)
        except reglages.ReglageError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        appliquer_acces_distant()  # l'interrupteur agit sans redemarrage
        BROKER.publish("reglages", {"maj": True})
        self._json(valeurs)

    def _televerser_logo(self) -> None:
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur <= 0:
            return self._error(HTTPStatus.BAD_REQUEST, "Fichier manquant")
        if longueur > 2 * 1024 * 1024:
            self._drain(longueur)
            self.close_connection = True
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Logo trop lourd (max 2 Mo)")

        donnees = self._read_exactly(longueur)
        if donnees is None:
            return self._error(HTTPStatus.BAD_REQUEST, "Transfert interrompu")

        mime = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        extensions = {"image/png": ".png", "image/jpeg": ".jpg",
                      "image/svg+xml": ".svg", "image/webp": ".webp"}
        if mime not in extensions:
            return self._error(HTTPStatus.BAD_REQUEST, "Format accepte : PNG, JPEG, SVG ou WebP")

        dossier = config.DATA_DIR / "marque"
        dossier.mkdir(parents=True, exist_ok=True)
        for ancien in dossier.glob("logo.*"):
            try:
                ancien.unlink()
            except OSError:
                pass
        nom = "logo" + extensions[mime]
        (dossier / nom).write_bytes(donnees)
        reglages.definir_logo(nom)
        BROKER.publish("reglages", {"maj": True})
        self._json({"logo": nom})

    def _supprimer_logo(self) -> None:
        dossier = config.DATA_DIR / "marque"
        for ancien in dossier.glob("logo.*"):
            try:
                ancien.unlink()
            except OSError:
                pass
        reglages.definir_logo(None)
        BROKER.publish("reglages", {"maj": True})
        self._json({"logo": None})

    def _connexion(self) -> None:
        """L'operateur saisit ses identifiants d'abonnement sur cette machine."""
        recu = self._read_json()
        if recu is None:
            return self._error(HTTPStatus.BAD_REQUEST, "Corps JSON attendu")
        email = str(recu.get("email", "")).strip()
        mot_de_passe = str(recu.get("mot_de_passe", ""))
        if not email or not mot_de_passe:
            return self._error(HTTPStatus.BAD_REQUEST, "Adresse e-mail et mot de passe requis")
        try:
            active = licence.activer(email, mot_de_passe, config.machine())
        except licence.LicenceError as exc:
            return self._error(HTTPStatus.UNAUTHORIZED, str(exc))
        self._json(active.public())

    def _inscrire_poste(self) -> None:
        """Un appareil declare ce qu'il est : borne, imprimante ou PC."""
        recu = self._read_json() or {}
        try:
            jeton = postes.inscrire(str(recu.get("role", "")), str(recu.get("nom", "")))
        except postes.PosteError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        self._json(
            postes.etat(jeton),
            HTTPStatus.CREATED,
            headers=self._poser_cookie_poste(jeton),
        )

    def _open_session(self) -> None:
        """La borne ouvre une session et recoit le lien a mettre dans son QR code."""
        ticket = STORE.create_ticket()
        port = self.server.server_address[1]
        payload = ticket.session()
        payload["url_envoi"] = f"{lien_client(port)}/e?s={ticket.token}"
        self._json(payload, HTTPStatus.CREATED)

    @staticmethod
    def _paiement_avant() -> bool:
        """La boutique exige-t-elle le reglement avant de livrer le code ?"""
        return reglages.tout()["paiement"].get("ordre") == "avant"

    def _code_visible(self, ticket) -> bool:
        return ticket.paid or not self._paiement_avant()

    def _get_session(self, token: str) -> None:
        ticket = STORE.get_by_token(token)
        if ticket is None:
            return self._error(HTTPStatus.NOT_FOUND, "Session inconnue ou expiree")
        self._json(ticket.session(self._code_visible(ticket)))

    def _reveler_code(self, token: str) -> None:
        """Le code de retrait, quand la boutique fait payer d'abord.

        Le refus est le point important : sans cette verification cote serveur,
        le mode « paiement avant » ne serait qu'un affichage, contournable en
        lisant la reponse de la validation.
        """
        ticket = STORE.get_by_token(token)
        if ticket is None or not ticket.validated:
            return self._error(HTTPStatus.NOT_FOUND, "Session inconnue ou expiree")
        if not self._code_visible(ticket):
            return self._error(
                HTTPStatus.PAYMENT_REQUIRED, "Le règlement n'a pas encore été encaissé"
            )
        self._json({"code": ticket.code})

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
            str(choix.get("orientation", catalogue.PORTRAIT)),
            choix.get("mesures"),
            choix.get("points"),
        )
        BROKER.publish("article", {"image": image.public()}, canal=token)
        self._json(image.public())

    def _validate(self, token: str) -> None:
        """L'operateur valide sur la borne : le code de retrait est revele."""
        ticket = STORE.validate(token)
        port = self.server.server_address[1]
        payload = ticket.session(self._code_visible(ticket))
        payload["url_paiement"] = f"{lien_client(port)}/p?j={ticket.payment_token}"
        BROKER.publish("depot", ticket.public())  # le poste de reception rafraichit sa liste
        BROKER.publish("validation", payload, canal=token)
        self._json(payload)

    def _get_payment(self, jeton: str) -> None:
        ticket = STORE.get_by_payment(jeton)
        if ticket is None or not ticket.validated:
            return self._error(HTTPStatus.NOT_FOUND, "Commande inconnue ou expiree")
        self._json({**ticket.paiement(), "config": reglages.tout()["paiement"]})

    def _pay(self, code: str) -> None:
        """Le commerçant confirme avoir encaisse.

        Volontairement reserve au poste de reception : la route exige le code de
        retrait, que le telephone du client ne connait pas. C'est la personne qui
        voit l'argent qui declare le paiement, pas celle qui doit le verser.

        Un encaissement verifie automatiquement viendrait se greffer ici, en
        interrogeant l'API du prestataire avant de basculer le statut.
        """
        ticket = STORE.get(code)
        if ticket is None:
            return self._error(HTTPStatus.NOT_FOUND, "Aucun depot avec ce code")
        ticket = STORE.mark_paid(ticket.payment_token)
        BROKER.publish("paiement", ticket.public())  # poste de reception
        # La borne recoit le code avec le paiement : c'est ce qui debloque son
        # affichage quand la boutique fait payer d'abord.
        BROKER.publish("paiement", ticket.session(True), canal=ticket.token)
        # Le telephone du client suit l'etat en direct sur le canal de sa commande.
        BROKER.publish("paiement", ticket.paiement(), canal=ticket.payment_token)
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


class PublicHandler(Handler):
    """Le serveur tel qu'il apparait au bout du tunnel.

    Meme code, deux portes : celle du reseau local sert tout, celle-ci ne sert
    que le telephone d'un client. La separation tient au **socket d'arrivee**,
    pas a un en-tete : `Host` et `X-Forwarded-For` se falsifient depuis
    n'importe ou, un port d'ecoute non. Il n'existe donc aucune requete, meme
    forgee, qui atteigne la reception ou les reglages par ce chemin.
    """

    PUBLIC = True

    def _jeton_poste(self) -> str | None:
        # Aucun role de ce cote. La route qui en attribue un n'est pas servie
        # ici, et un cookie recopie a la main ne donne rien de plus que ce que
        # la surface publique sert deja.
        return None


# --- demarrage -----------------------------------------------------------------


def _purge_loop() -> None:
    while True:
        time.sleep(300)
        try:
            if STORE.purge():
                BROKER.publish("purge", {"auto": True})
        except Exception:  # pragma: no cover - le nettoyage ne doit jamais tuer le thread
            pass


def build_server(host: str, port: int, attempts: int = 20, handler=Handler) -> KioskServer:
    """Ouvre le serveur, en glissant sur le port suivant s'il est deja pris."""
    last: OSError | None = None
    for offset in range(attempts):
        try:
            return KioskServer((host, port + offset), handler)
        except OSError as exc:
            last = exc
    raise SystemExit(f"Aucun port libre entre {port} et {port + attempts - 1} ({last})")


def ouvrir_porte_publique(port_principal: int) -> KioskServer | None:
    """Seconde porte, sur la boucle locale, ou vient se brancher le tunnel.

    Elle ne glisse pas de port en port comme la premiere : le tunnel est
    configure une fois pour toutes sur une adresse fixe, et un repli silencieux
    le laisserait pointer dans le vide sans que personne s'en apercoive.
    """
    port = config.port_public(port_principal)
    if not port:
        return None
    try:
        return KioskServer((config.PUBLIC_HOST, port), PublicHandler)
    except OSError as exc:
        print(f"\n  Porte publique non ouverte sur le port {port} : {exc}")
        print("  Le depot a distance restera indisponible.\n")
        return None


def serve(
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = False,
    atelier: str | None = None,
) -> None:
    global PORTE_PUBLIQUE

    server = build_server(host or config.HOST, port or config.PORT)
    actual_port = server.server_address[1]

    porte = ouvrir_porte_publique(actual_port)
    if porte is not None:
        PORTE_PUBLIQUE = porte.server_address[1]
        threading.Thread(target=porte.serve_forever, daemon=True).start()
        # Le tunnel met quelques secondes a s'ouvrir : on ne fait pas attendre
        # le demarrage, la page des reglages suivra la progression en direct.
        threading.Thread(target=appliquer_acces_distant, daemon=True).start()

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

    if porte is not None:
        mode = reglages.tout()["acces_distant"].get("mode", "aucun")
        if mode == "aucun":
            print("\n  Depot a distance    : desactive.")
            print("  Les clients doivent etre sur le Wi-Fi de la boutique.")
            print("  Pour l'ouvrir : Reglages > Depot a distance.")
        elif mode == "manuel":
            print(f"\n  Depot a distance    : {reglages.url_publique()}")
        elif tunnel.chemin_outil() is None:
            print("\n  Depot a distance    : demande, mais l'outil de connexion")
            print("  est absent de cette installation (dossier outils/).")
        else:
            print("\n  Depot a distance    : ouverture de la connexion en cours...")
            print("  L'adresse apparaitra dans Reglages > Depot a distance.")

    print(f"\n  Depots conserves {config.RETENTION_HOURS} h dans {config.DATA_DIR}")
    print("  Ctrl+C pour arreter.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arret du Symp's Kiosk.")
    finally:
        annonceur.arreter()
        tunnel.TUNNEL.arreter()
        if porte is not None:
            porte.shutdown()
            porte.server_close()
        server.shutdown()
        server.server_close()
