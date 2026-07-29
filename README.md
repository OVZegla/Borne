# Symp's Kiosk

Petite application locale pour envoyer des photos depuis son téléphone vers une
borne, puis les récupérer sur un autre appareil — typiquement le poste relié à
l'imprimante.

Le parcours :

1. La borne affiche un **QR code**.
2. Le client le scanne avec son téléphone et envoie ses photos.
3. Les photos s'affichent **en grand sur la borne**, au fur et à mesure.
4. Pour chaque photo, il choisit sa **matière**, ses **dimensions** et sa
   **forme** — l'aperçu montre le tirage tel qu'il sera, et le prix s'affiche.
5. Il **valide** : un **code à 4 chiffres** et un **QR code de paiement** apparaissent.
6. À la réception, le code ouvre le dépôt, avec le détail des tirages et la
   mention **En attente** ou **Payé**, qui bascule en direct.

Aucune dépendance à installer : **Python 3 suffit**, tout le reste est écrit avec
la bibliothèque standard.

---

## Plusieurs machines dans la boutique

Au lancement, l'application cherche sur le réseau local une machine du même
atelier déjà démarrée :

- **elle en trouve une** → ce poste s'y connecte et ouvre son navigateur dessus.
  Rien à configurer, aucune adresse à taper ;
- **elle n'en trouve pas** → cette machine devient l'**hôte** : elle stocke les
  dépôts et se signale aux autres.

Concrètement : lancez l'application sur la machine qui garde les photos, puis sur
la borne et sur le poste de réception. Elles se trouvent toutes seules.

```bash
./start.sh            # rôle choisi automatiquement
./start.sh --hote     # forcer cette machine comme hôte
./start.sh --poste    # se connecter uniquement, ne jamais héberger
```

L'identifiant d'atelier (`atelier.txt` dans le dossier de données, ou
`SYMPS_ATELIER`) évite qu'une
borne rejoigne l'hôte d'une autre boutique sur un réseau partagé. Ce n'est pas un
secret : toutes les machines doivent être sur le même réseau de confiance.

## Démarrer sur Windows

C'est la plateforme des postes en boutique.

Double-cliquez sur **`Symps Kiosk.bat`**.

> **Windows n'a pas Python préinstallé**, contrairement au Mac. Au premier
> déploiement, installez-le depuis <https://www.python.org/downloads/> en cochant
> **« Add python.exe to PATH »**. Le lanceur affiche ce message si Python manque.
>
> Voir plus bas : pour livrer à des clients, l'objectif est un `.exe` autonome
> qui embarque Python — ils n'auront alors rien à installer.

**Au premier lancement, Windows affiche une alerte du pare-feu** : autorisez
l'accès sur les **réseaux privés**. Sans cela, le téléphone ne pourra pas
atteindre la borne et les postes ne se trouveront pas entre eux.

Les dépôts sont écrits dans `%LOCALAPPDATA%\Symp's Kiosk\depots`, et non à côté
du programme : l'application peut ainsi être installée dans un dossier en
lecture seule.

## Démarrer sur un Mac

La version Mac sert surtout aux essais : les postes en boutique sont sous Windows.

Dans le Finder, double-cliquez sur **`Symp's Kiosk.command`**.

Ou depuis le Terminal :

```bash
cd Borne
./start.sh
```

Le navigateur s'ouvre tout seul sur la page de dépôt. La console affiche aussi
l'adresse à utiliser depuis les autres appareils :

```
  Symp's Kiosk - cette machine est l'hote.

  Sur cette machine   : http://localhost:8080
  Depuis un autre app.: http://192.168.1.42:8080

  Les autres postes de la boutique s'y connecteront tout seuls.
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
grand, avec les options de tirage à côté :

- **Matière** — Plexiglas, Métal, Dibond, Toile, Cadre, Papier, Bois, Verre
- **Dimensions** — 25×30, 30×40, 40×50, 40×60, 50×70, 20×20, 30×30, 40×40, 50×50 cm
- **Orientation** — portrait ou paysage, **présélectionnée d'après la photo**
- **Coupe** — Format initial, Diamant, Triangle, Cercle

L'aperçu prend les proportions du format choisi, son orientation et la découpe
demandée : le client voit le tirage tel qu'il sera, recadrage compris. Le prix
s'actualise à chaque changement, et l'orientation ne le change jamais.

> **L'orientation évite le mauvais recadrage** : une photo paysage bascule
> d'elle-même sur un cadre paysage. Un format carré n'a pas d'orientation, le
> choix disparaît alors.

> **Une matière qui ne se découpe pas** (une toile sur châssis) ramène la coupe
> au rectangle. Les autres se grisent, et le serveur refuse la combinaison même
> si on la force.

Ces listes sont celles livrées par défaut : chaque boutique compose les siennes
dans les **réglages**.

Avec plusieurs photos, une bande de vignettes permet de passer de l'une à
l'autre ; celles dont le tirage n'est pas encore choisi ont un contour orange.
Un récapitulatif chiffré s'affiche sous la bande. Trois boutons :

- **Valider et obtenir mon code** — actif seulement quand chaque photo a son
  tirage ; clôture le dépôt, révèle le code et le QR de paiement
- **Ajouter d'autres photos** — revient au QR code, la session reste ouverte
- **Tout annuler** — supprime les photos reçues et repart à zéro

### Sur le téléphone du client

Scanner le QR code ouvre la page d'envoi. Deux boutons : **Prendre une photo**
(déclenche l'appareil photo) ou **Choisir dans ma galerie**. Une fois l'envoi
terminé, la page invite à retourner à la borne.

Pas de QR code lisible ? L'adresse est écrite en toutes lettres sous le code.

### Le paiement

Après validation, la borne affiche un second QR code, distinct de celui d'envoi.
Le client le scanne et arrive sur le récapitulatif de sa commande avec le total.

Deux modes, au choix dans les **réglages** :

- **Règlement au comptoir** — le bouton signale le paiement à la réception ;
- **Lien de paiement** — le client est envoyé vers votre page PayPal, SumUp ou
  Stripe.

> **Dans les deux cas, le règlement est confirmé à la réception.** Sans
> raccordement à l'API de votre prestataire, la borne ne peut pas savoir seule
> qu'un paiement a abouti. Pour une confirmation automatique, tout se passe dans
> `_pay()` de `kiosk/server.py` : c'est le seul endroit qui bascule le statut, et
> la vérification doit rester côté serveur.

### Sur le poste d'impression

Trois façons d'arriver au dépôt :

- ouvrir `http://<adresse-de-la-borne>:8080/recuperer` et saisir le code
- scanner le QR code affiché sur la borne après validation
- cliquer sur le dépôt dans la liste **Derniers dépôts**, qui se met à jour en
  direct sans rafraîchir la page

Chaque photo affiche le tirage commandé (matière, format, forme) et son prix,
avec **Imprimer** (page épurée, prête pour `⌘P`) et **Télécharger**. Un bouton
**Tout télécharger (.zip)** récupère le dépôt entier. Le badge **En attente** /
**Payé** est visible dans la liste comme sur le détail, et bascule en direct dès
que le client règle.

> Un dépôt n'apparaît à la réception **qu'une fois validé** sur la borne : les
> photos en cours d'envoi restent invisibles côté imprimante.

---

## Réglages

Tout se règle par variables d'environnement, sans toucher au code :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SYMPS_PORT` | `8080` | port d'écoute (glisse au port suivant s'il est pris) |
| `SYMPS_HOST` | `0.0.0.0` | interface d'écoute |
| `SYMPS_DISCOVERY_PORT` | `8079` | port UDP d'appairage des machines |
| `SYMPS_ATELIER` | auto | identifiant partagé par les machines d'une boutique |
| `SYMPS_DATA` | dossier système¹ | dossier de stockage des dépôts |
| `SYMPS_RETENTION_HOURS` | `24` | conservation d'un dépôt, à partir de sa validation |
| `SYMPS_DRAFT_HOURS` | `2` | oubli d'une session ouverte mais restée vide |
| `SYMPS_MAX_MB` | `25` | taille maximale par fichier |
| `SYMPS_MAX_FILES` | `20` | nombre de fichiers par dépôt |
| `SYMPS_LICENCE_URL` | — | serveur d'abonnement ; vide = pas de connexion exigée |
| `SYMPS_LICENCE_CLE` | — | clé publique servant à vérifier les licences |
| `SYMPS_LICENCE_GRACE_HEURES` | `72` | fonctionnement hors ligne toléré |
| `SYMPS_VERBOSE` | — | à définir pour journaliser chaque requête |

¹ Par défaut, l'emplacement inscriptible propre à chaque système :

| Système | Emplacement des dépôts |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Symp's Kiosk\depots` |
| macOS | `~/Library/Application Support/Symp's Kiosk/depots` |
| Linux | `$XDG_DATA_HOME/symps-kiosk/depots` |

Exemple :

```bash
SYMPS_PORT=9000 SYMPS_RETENTION_HOURS=2 ./start.sh
```

Sous Windows :

```bat
set SYMPS_PORT=9000
"Symps Kiosk.bat"
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
- Les trois identifiants d'un dépôt sont **des secrets distincts** : le jeton
  d'envoi (QR de la borne), le jeton de paiement (QR de règlement) et le code de
  retrait à 4 chiffres. Scanner un QR ne permet jamais de récupérer un dépôt, et
  le code de retrait n'apparaît sur aucune page de paiement.
- Le statut de paiement est **déclaratif** tant qu'aucun prestataire n'est
  branché : n'importe qui possédant le lien de règlement peut marquer la
  commande comme payée. À vérifier au comptoir, ou à sécuriser en branchant un
  encaissement réel (voir plus haut).
- Formats acceptés : JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC/HEIF et PDF. Les
  HEIC et PDF se téléchargent bien, mais l'aperçu et l'impression navigateur ne
  fonctionnent que pour les formats que le navigateur sait afficher.

---

## Abonnement

Quand `SYMPS_LICENCE_URL` est renseignée — c'est le cas des versions livrées aux
clients — l'application demande une **connexion au lancement**. Tant qu'aucun
abonnement actif n'est enregistré, toutes les pages renvoient vers `/connexion`.

Une fois connectée, la boutique reçoit une licence signée qui lui permet de
fonctionner **72 h sans Internet**. C'est aussi le compte qui appaire les
machines entre elles sur le réseau local.

Sur une copie de développement, la variable est vide : l'application tourne sans
abonnement, comme aujourd'hui.

**Voir [ABONNEMENT.md](ABONNEMENT.md)** pour l'hébergement du service de licences
et la gestion des abonnements avec Stripe.

## Livrer aux clients : ce qui reste à faire

Aujourd'hui l'application se lance par un script et suppose Python installé.
Pour la distribuer à des boutiques par abonnement, il manque :

**1. Un `.exe` autonome.** PyInstaller produit un exécutable unique qui embarque
Python : le client n'installe plus rien. C'est l'étape qui débloque tout le reste.

**2. La signature du code.** Sans certificat, **SmartScreen** affiche un
avertissement dissuasif au premier lancement chez chaque client. Comptez un
certificat de signature (les certificats EV donnent une réputation immédiate).
L'équivalent Mac est la notarisation Apple, qui suppose un compte développeur.

**3. Une règle de pare-feu posée à l'installation**, pour éviter de demander au
commerçant de cliquer sur la bonne option de l'alerte Windows.

**4. L'activation par abonnement.** Le compte validerait l'abonnement et
appairerait les machines : l'identifiant d'atelier utilisé aujourd'hui pour la
découverte réseau est prévu pour devenir celui du compte. Une vérification hors
ligne (signature vérifiable sans réseau, avec période de grâce) évite qu'une
coupure Internet empêche la boutique de vendre.

## Personnaliser la boutique

La page **Réglages** (`/reglages`) appartient au commerçant. Tout ce qui s'y
trouve s'applique aussitôt sur tous les postes :

- **Marque** — nom de la boutique, couleur principale, couleur d'accent, et son
  logo. Celui de Symp's et la mention « Symp's Kiosk » restent présents à côté,
  sur toutes les pages.
- **Matières** — librement créées : un nom, un coefficient de prix, et le fait
  qu'elles se découpent ou non. Rien n'est imposé.
- **Formats** — librement créés : nom, largeur, hauteur et prix de base.
  Saisissez-les en portrait, le client choisit lui-même portrait ou paysage.
- **Coupes** — librement créées : un nom maison (« Hublot »…), une géométrie
  parmi celles que la borne sait dessiner, et un supplément. **Une case unique
  supprime tout le menu** pour une boutique sans machine de découpe : le serveur
  refuse alors toute découpe, même forcée par l'API.
- **Encaissement** — au comptoir, ou vers votre propre lien de paiement.

Le prix d'un tirage vaut toujours
`prix du format × coefficient de la matière + supplément de coupe`.

## Remplacer le logo

L'en-tête de toutes les pages affiche `web/assets/logo-symps.svg`. Ce fichier est
une **reconstitution vectorielle** de la signature Symp's : les deux crochets
sont exacts, mais le mot « Symp's » est composé avec la police système, pas avec
la police d'origine.

Pour mettre votre logo officiel : **écrasez ce fichier** par le vôtre (SVG de
préférence, format horizontal, environ 2,6 fois plus large que haut). Aucune
autre modification n'est nécessaire, les cinq pages le reprendront.

`web/assets/logo.svg` est la version carrée, utilisée uniquement comme favicon :
une signature horizontale serait illisible dans un onglet.

## Organisation du code

```
symps.py               point d'entrée
Symps Kiosk.bat        lanceur Windows (double-clic)
start.sh               lanceur macOS / Linux (vérifie Python 3)
Symp's Kiosk.command   lanceur double-cliquable depuis le Finder
kiosk/
  config.py            réglages et variables d'environnement
  reseau.py            appairage automatique des machines en LAN
  reglages.py          réglages de la boutique : marque, catalogue, tarifs
  catalogue.py         calcul des prix et des libellés, orientation
  server.py            serveur HTTP, routes, flux temps réel (SSE)
  storage.py           dépôts, articles, paiement, expiration
  imagemeta.py         dimensions lues dans les en-têtes (sans Pillow)
  qr.py                générateur de QR code autonome
  licence.py           abonnement : activation, licence signée, hors ligne
web/
  connexion.html       écran de connexion à l'abonnement
  reglages.html        personnalisation : marque, catalogue, encaissement
  index.html           la borne : QR, photos en grand, choix du tirage, code
  envoyer.html         le téléphone : envoi des photos après scan du QR
  paiement.html        le téléphone : récapitulatif et règlement
  recuperer.html       la réception : saisie du code, galerie, statut de paiement
  impression.html      vue d'impression d'une image
  assets/              CSS, JavaScript et logos
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
| `POST` | `/api/sessions/<jeton>/images/<id>/article` | choisit matière, format et forme |
| `POST` | `/api/sessions/<jeton>/valider` | clôture le dépôt et révèle le code |
| `GET` | `/api/catalogue` | matières, formats, coupes et grille de prix |
| `GET` `POST` `DELETE` | `/api/reglages` | réglages de la boutique |
| `POST` `DELETE` | `/api/reglages/logo` | logo de la boutique |
| `GET` | `/assets/theme.css` | couleurs de la boutique, feuille générée |
| `GET` | `/api/paiement/<jeton>` | récapitulatif de la commande et son statut |
| `POST` | `/api/paiement/<jeton>/regler` | enregistre le règlement |
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
| `GET` | `/p?j=<jeton>` | lien court encodé dans le QR code de paiement |
| `GET` | `/r?c=<code>` | lien court vers un dépôt validé |
