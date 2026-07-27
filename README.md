# Symp's Kiosk

Petite application locale pour envoyer des photos depuis son téléphone vers une
borne, puis les récupérer sur un autre appareil — typiquement le poste relié à
l'imprimante.

Le parcours :

1. La borne affiche un **QR code**.
2. Le client le scanne avec son téléphone et envoie ses photos.
3. Les photos s'affichent **en grand sur la borne**, au fur et à mesure.
4. Le client **valide** sur la borne : un **code à 4 chiffres** apparaît.
5. Au poste d'impression, ce code ouvre le dépôt.

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

### Sur la borne

Laissez `http://localhost:8080` ouvert en plein écran. La page affiche en
permanence le QR code d'envoi et attend les photos.

Dès qu'une photo arrive, la borne bascule automatiquement dessus et l'affiche en
grand. Avec plusieurs photos, une bande de vignettes permet de passer de l'une à
l'autre. Trois boutons :

- **Valider et obtenir mon code** — clôture le dépôt et révèle le code
- **Ajouter d'autres photos** — revient au QR code, la session reste ouverte
- **Tout annuler** — supprime les photos reçues et repart à zéro

### Sur le téléphone du client

Scanner le QR code ouvre la page d'envoi. Deux boutons : **Prendre une photo**
(déclenche l'appareil photo) ou **Choisir dans ma galerie**. Une fois l'envoi
terminé, la page invite à retourner à la borne.

Pas de QR code lisible ? L'adresse est écrite en toutes lettres sous le code.

### Sur le poste d'impression

Trois façons d'arriver au dépôt :

- ouvrir `http://<adresse-de-la-borne>:8080/recuperer` et saisir le code
- scanner le QR code affiché sur la borne après validation
- cliquer sur le dépôt dans la liste **Derniers dépôts**, qui se met à jour en
  direct sans rafraîchir la page

Chaque image propose **Imprimer** (page épurée, prête pour `⌘P`) et
**Télécharger**. Un bouton **Tout télécharger (.zip)** récupère le dépôt entier.

> Un dépôt n'apparaît au poste d'impression **qu'une fois validé** sur la borne :
> les photos en cours d'envoi restent invisibles côté imprimante.

---

## Réglages

Tout se règle par variables d'environnement, sans toucher au code :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SYMPS_PORT` | `8080` | port d'écoute (glisse au port suivant s'il est pris) |
| `SYMPS_HOST` | `0.0.0.0` | interface d'écoute |
| `SYMPS_DATA` | `./depots` | dossier de stockage des dépôts |
| `SYMPS_RETENTION_HOURS` | `24` | conservation d'un dépôt, à partir de sa validation |
| `SYMPS_DRAFT_HOURS` | `2` | oubli d'une session ouverte mais restée vide |
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

- **Le téléphone doit être sur le même réseau que la borne** (même Wi-Fi). C'est
  le point qui coince le plus souvent : un téléphone resté en 4G n'atteindra pas
  l'adresse du QR code. L'adresse `localhost` ne fonctionne, elle, que sur la
  machine qui héberge la borne.
- **Les dépôts expirent** au bout de 24 h par défaut, à compter de leur
  validation : les fichiers sont alors effacés du disque.
- **Rien ne sort du réseau local.** Aucun compte, aucun envoi vers l'extérieur ;
  les images restent dans le dossier `depots/`.
- Il n'y a **pas d'authentification** : toute personne sur le réseau qui connaît
  le code peut récupérer le dépôt. C'est adapté à un réseau de confiance
  (boutique, atelier), pas à un réseau public ouvert.
- Le jeton du QR code et le code de retrait sont **deux secrets distincts** :
  scanner le QR permet d'envoyer des photos, jamais de récupérer un dépôt.
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
  index.html           la borne : QR code, photos en grand, validation
  envoyer.html         le téléphone : envoi des photos après scan du QR
  recuperer.html       le poste d'impression : saisie du code, galerie
  impression.html      vue d'impression d'une image
  assets/              CSS, JavaScript et logo
samples/               vos images d'exemple
depots/                dépôts créés à l'exécution (ignoré par git)
```

### Interface HTTP

Un dépôt a deux identifiants : le **jeton** (`token`), secret d'envoi encodé dans
le QR code de la borne, et le **code** à 4 chiffres, révélé à la validation et
utilisé pour le retrait.

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| `POST` | `/api/sessions` | ouvre une session, renvoie le jeton et l'URL du QR |
| `GET` | `/api/sessions/<jeton>` | état de la session (sans le code) |
| `POST` | `/api/sessions/<jeton>/images` | envoie une photo (corps = octets bruts) |
| `POST` | `/api/sessions/<jeton>/valider` | clôture le dépôt et révèle le code |
| `DELETE` | `/api/sessions/<jeton>` | abandonne la session en cours |
| `GET` | `/api/depots` | liste les dépôts **validés** |
| `GET` | `/api/depots/<code>` | contenu d'un dépôt validé |
| `GET` | `/api/depots/<code>/zip` | archive du dépôt |
| `DELETE` | `/api/depots/<code>` | supprime un dépôt |
| `GET` | `/media/<id>` | l'image (`?dl=1` pour forcer le téléchargement) |
| `DELETE` | `/api/images/<id>` | supprime une image |
| `GET` | `/api/evenements` | flux SSE public (dépôts validés, suppressions) |
| `GET` | `/api/evenements?session=<jeton>` | flux SSE d'une seule borne |
| `GET` | `/qr.svg?d=<url>` | QR code en SVG |
| `GET` | `/e?s=<jeton>` | lien court encodé dans le QR code de la borne |
| `GET` | `/r?c=<code>` | lien court vers un dépôt validé |
