# Symp's Kiosk

Petite application locale pour déposer des images sur une borne et les récupérer
sur un autre appareil — typiquement le poste relié à l'imprimante.

Le principe est celui d'une consigne : on dépose des fichiers sur la borne, elle
rend un **code à 4 chiffres** (et un QR code), et n'importe quel appareil du même
réseau récupère le dépôt avec ce code.

Aucune dépendance à installer : **Python 3 suffit**, tout le reste est écrit avec
la bibliothèque standard.

---

## Démarrer sur un Mac

Dans le Finder, double-cliquez sur **`Symp's Kiosk.command`**.

Ou depuis le Terminal :

```bash
cd Borne
./start.sh
```

Le navigateur s'ouvre tout seul sur la page de dépôt. La console affiche aussi
l'adresse à utiliser depuis les autres appareils :

```
  Symp's Kiosk est demarre.

  Sur cette machine   : http://localhost:8080
  Depuis un autre app.: http://192.168.1.42:8080
```

> **Au premier lancement**, macOS peut refuser d'exécuter le fichier `.command`.
> Faites alors un clic droit dessus → **Ouvrir** → **Ouvrir**, une seule fois.
> Si Python 3 manque, installez les outils Xcode avec `xcode-select --install`.

Pour arrêter la borne : `Ctrl+C` dans la fenêtre du Terminal.

---

## Utilisation

### Sur la borne — déposer

1. Ouvrez `http://localhost:8080`
2. Glissez vos images dans la zone de dépôt (ou cliquez pour parcourir, ou
   collez avec `⌘V`, ou photographiez depuis un téléphone)
3. Cliquez sur **Terminer** : le code à 4 chiffres et le QR code s'affichent

### Sur l'imprimante — récupérer

Trois façons d'arriver au dépôt :

- ouvrir `http://<adresse-de-la-borne>:8080/recuperer` et saisir le code
- scanner le QR code affiché sur la borne, qui ouvre directement le dépôt
- cliquer sur le dépôt dans la liste **Derniers dépôts**, qui se met à jour en
  direct sans rafraîchir la page

Chaque image propose **Imprimer** (page épurée, prête pour `⌘P`) et
**Télécharger**. Un bouton **Tout télécharger (.zip)** récupère le dépôt entier.

---

## Réglages

Tout se règle par variables d'environnement, sans toucher au code :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SYMPS_PORT` | `8080` | port d'écoute (glisse au port suivant s'il est pris) |
| `SYMPS_HOST` | `0.0.0.0` | interface d'écoute |
| `SYMPS_DATA` | `./depots` | dossier de stockage des dépôts |
| `SYMPS_RETENTION_HOURS` | `24` | durée de conservation d'un dépôt |
| `SYMPS_MAX_MB` | `25` | taille maximale par fichier |
| `SYMPS_MAX_FILES` | `20` | nombre de fichiers par dépôt |
| `SYMPS_VERBOSE` | — | à définir pour journaliser chaque requête |

Exemple :

```bash
SYMPS_PORT=9000 SYMPS_RETENTION_HOURS=2 ./start.sh
```

Options en ligne de commande : `./start.sh --port 9000 --no-browser`

---

## Bon à savoir

- **Les deux appareils doivent être sur le même réseau** (même Wi-Fi, ou câble).
  L'adresse `localhost` ne fonctionne que sur la machine qui héberge la borne.
- **Les dépôts expirent** au bout de 24 h par défaut : les fichiers sont alors
  effacés du disque. La durée est fixée à la création du dépôt.
- **Rien ne sort du réseau local.** Aucun compte, aucun envoi vers l'extérieur ;
  les images restent dans le dossier `depots/`.
- Il n'y a **pas d'authentification** : toute personne sur le réseau qui connaît
  le code peut récupérer le dépôt. C'est adapté à un réseau de confiance
  (boutique, atelier), pas à un réseau public ouvert.
- Formats acceptés : JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC/HEIF et PDF. Les
  HEIC et PDF se téléchargent bien, mais l'aperçu et l'impression navigateur ne
  fonctionnent que pour les formats que le navigateur sait afficher.

---

## Organisation du code

```
symps.py               point d'entrée
start.sh               lanceur (vérifie Python 3)
Symp's Kiosk.command   lanceur double-cliquable depuis le Finder
kiosk/
  config.py            réglages et variables d'environnement
  server.py            serveur HTTP, routes, flux temps réel (SSE)
  storage.py           dépôts, codes, écriture disque, expiration
  imagemeta.py         dimensions lues dans les en-têtes (sans Pillow)
  qr.py                générateur de QR code autonome
web/
  index.html           page de dépôt (la borne)
  recuperer.html       page de récupération (l'imprimante)
  impression.html      vue d'impression d'une image
  assets/              CSS, JavaScript et logo
samples/               vos images d'exemple
depots/                dépôts créés à l'exécution (ignoré par git)
```

### Interface HTTP

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| `POST` | `/api/depots` | ouvre un dépôt, renvoie son code |
| `POST` | `/api/depots/<code>/images` | ajoute une image (corps = octets bruts) |
| `GET` | `/api/depots` | liste les dépôts récents |
| `GET` | `/api/depots/<code>` | contenu d'un dépôt |
| `GET` | `/api/depots/<code>/zip` | archive du dépôt |
| `DELETE` | `/api/depots/<code>` | supprime un dépôt |
| `GET` | `/media/<id>` | l'image (`?dl=1` pour forcer le téléchargement) |
| `DELETE` | `/api/images/<id>` | supprime une image |
| `GET` | `/api/evenements` | flux SSE des dépôts et ajouts |
| `GET` | `/qr.svg?d=<url>` | QR code en SVG |
| `GET` | `/r?c=<code>` | lien court encodé dans le QR code |
