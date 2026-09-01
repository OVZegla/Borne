# Symp's Kiosk

Petite application locale pour envoyer des photos depuis son téléphone vers une
borne, puis les récupérer sur un autre appareil — typiquement le poste relié à
l'imprimante.

Le parcours :

1. La borne affiche un **QR code**.
2. Le client le scanne avec son téléphone et envoie ses photos.
3. Les photos s'affichent **en grand sur la borne**, au fur et à mesure.
4. Pour chaque photo, il choisit son **support**, son **format** et sa
   **forme** — l'aperçu montre le tirage tel qu'il sera, et le prix s'affiche.
5. Il **valide** : un **code à 4 chiffres** et un **QR code de paiement**
   apparaissent — ou, si la boutique fait payer d'abord, le QR de règlement
   d'abord et le code seulement après encaissement.
6. À la réception, le code ouvre le dépôt, avec le détail des tirages et la
   mention **En attente** ou **Payé**, qui bascule en direct.

Aucune dépendance à installer : **Python 3 suffit**, tout le reste est écrit avec
la bibliothèque standard.

---

## Trois sortes de postes

Un appareil n'a pas les mêmes droits selon ce qu'il est. Le choix se fait au
premier chargement, et il est retenu :

| Poste | Ce qu'il voit | Sa page d'accueil |
| --- | --- | --- |
| **Borne** | l'écran face au client, et rien d'autre | `/` |
| **Imprimante** | réception, impression, réglages | `/recuperer` |
| **PC** | tableau de bord, réception, impression, réglages | `/tableau` |

**La borne est cloisonnée.** Elle n'atteint ni la réception, ni les réglages, ni
le tableau de bord : un client qui tapote l'écran ne doit pas tomber sur vos
tarifs ou sur les dépôts des autres. Ce n'est pas qu'un menu allégé — le serveur
lui **refuse** ces routes, et une adresse tapée à la main la ramène sur son
écran.

Le rôle vit dans un jeton tiré au hasard, posé en cookie. Un appareil ne peut
donc pas s'inventer un rôle en modifiant son cookie : il ne connaît pas les
jetons des autres. Le bouton **« Changer le rôle de cet appareil »**, en pied de
page des postes de gestion, permet de repartir sur l'écran de choix.

Le **téléphone du client** n'est pas un poste : il n'a aucun rôle, et n'atteint
que la page d'envoi et la page de règlement, dont le secret est le jeton contenu
dans le QR code.

### Comment on se connecte

L'abonnement ne se saisit **qu'une fois**, sur la machine qui héberge
l'application, et cette machine déclare alors si elle est le PC ou l'imprimante.
Les autres appareils arrivent par le réseau local : ils n'ont **rien à saisir**,
juste à dire ce qu'ils sont.

> **À savoir** : sur le réseau local, qui atteint la borne peut aussi ouvrir
> l'écran de choix et se déclarer « PC ». Sur le Wi-Fi de la boutique c'est sans
> conséquence ; si vos clients partagent le réseau de vos machines, il faudra un
> code d'accès sur ce choix — il n'y en a pas aujourd'hui. C'est justement
> pourquoi le dépôt à distance ne passe **pas** par cet écran : voir
> [Déposer depuis n'importe quel réseau](#déposer-depuis-nimporte-quel-réseau).

## Le tableau de bord (poste PC)

`/tableau` ouvre sur ce qu'un gérant regarde en arrivant :

- **les quatre chiffres du jour** — encaissé, en attente de paiement, dépôts,
  panier moyen ;
- **ce qui demande une action** — les dépôts à encaisser et ceux qui expirent
  dans moins de trois heures, cliquables pour ouvrir le dépôt ;
- **la recette des sept derniers jours**, en barres ;
- **ce qui se vend** — le classement des supports et des formats, en nombre de
  tirages et en recette ;
- **les postes de la boutique** vus dans les cinq dernières minutes.

Tout se recalcule à la demande depuis les dépôts en cours : les chiffres portent
donc sur la **période de conservation** (24 h par défaut). Ce n'est pas une
comptabilité au long cours. La page suit la boutique en direct — un encaissement
au comptoir s'y voit sans rafraîchir.

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

## Déposer depuis n'importe quel réseau

Le QR code de la borne contient une adresse. Tant que c'est celle du réseau local
— `http://192.168.1.42:8080` — **seul un téléphone posé sur le même Wi-Fi peut
déposer** : une adresse privée n'est routable que de l'intérieur. Un client en 4G
scanne le QR et n'arrive nulle part.

Pour lever ça, la boutique ouvre un **tunnel sortant** vers sa machine hôte, ce
qui lui donne une adresse publique en `https`, et la déclare dans
**Réglages → Dépôt à distance**. Les QR codes portent alors cette adresse, et le
dépôt fonctionne depuis n'importe quel réseau — sans donner le Wi-Fi de la
boutique aux clients, et sans ouvrir le moindre port sur la box.

### Les deux portes

Une adresse publique qui mènerait au serveur entier mettrait la réception, le
tableau de bord et les tarifs sur Internet. L'application écoute donc sur **deux
portes distinctes** :

| Porte | Écoute sur | Sert |
| --- | --- | --- |
| **locale** | toutes les interfaces, port `8080` | tout : borne, réception, impression, tableau, réglages |
| **publique** | `127.0.0.1` uniquement, port `8081` | l'envoi des photos et le règlement, rien d'autre |

La porte publique n'est ouverte **que sur la boucle locale** : le tunnel, qui
tourne sur cette même machine, l'atteint ; le reste du réseau de la boutique,
non. C'est là — et **nulle part ailleurs** — que le tunnel se branche.

La séparation tient au **port d'arrivée**, pas à un en-tête : `Host` et
`X-Forwarded-For` se falsifient depuis n'importe où, un port d'écoute non. Aucune
requête, même forgée, n'atteint la réception par ce chemin. Ce que la porte
publique sert est une **liste blanche** (`SURFACE_PUBLIQUE` dans `server.py`) :
une route ajoutée au serveur n'y apparaît que si on l'y met, si bien qu'un oubli
ferme la porte au lieu de l'ouvrir.

Concrètement, au bout du tunnel :

- `/envoyer`, `/paiement` et leurs API, `/e`, `/p`, les feuilles de style ;
- **rien** d'autre : `/tableau`, `/recuperer`, `/reglages`, `/impression`,
  `/connexion`, `/api/depots`, `/api/poste`… répondent `404`. Pas `403` : depuis
  Internet, rien ne laisse deviner qu'il y a une boutique derrière.
- aucun rôle n'existe de ce côté. La route qui en attribue un n'y est pas servie,
  et un cookie de rôle recopié à la main n'y donne rien de plus.
- le flux d'événements exige le jeton d'une session : sans lui, l'abonnement
  porterait sur le canal général de la boutique, qui diffuse **tous** les dépôts.

### Mettre en place le tunnel

Au démarrage, l'application affiche l'adresse de sa porte publique :

```
  Porte publique      : http://127.0.0.1:8081   (envoi et reglement seulement)
```

Avec [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
(gratuit, rien à ouvrir sur la box) :

```bash
cloudflared tunnel --url http://127.0.0.1:8081
```

La commande affiche une adresse en `https://…` : reportez-la dans
**Réglages → Dépôt à distance**, cochez la case, enregistrez. Les QR codes
suivants la portent. Pour une boutique installée, préférez un *tunnel nommé*, qui
garde la même adresse d'un redémarrage à l'autre. `ngrok` et Tailscale Funnel
font la même chose.

Le `https` n'est pas décoratif : hors contexte sécurisé, les navigateurs mobiles
refusent l'accès à l'appareil photo. Une adresse en `http://` est donc refusée à
la saisie.

> **À savoir** : cette adresse est publique, et le seul secret qui protège un
> dépôt est le jeton contenu dans le QR code — 128 bits tirés au hasard, un par
> session, effacé avec le dépôt. Personne ne devine celui d'un autre client, mais
> quiconque reçoit le lien peut ajouter des photos à ce dépôt tant qu'il n'est pas
> validé. Le débit d'envoi n'est pas limité par l'application : si votre tunnel
> sait le faire, un plafond de requêtes n'est pas du luxe.

Sans adresse déclarée, rien ne change : les QR codes gardent l'adresse du réseau
local. Pour ne pas ouvrir la porte publique du tout, lancez avec
`SYMPS_PUBLIC_PORT=off`.

Une fois l'adresse cochée, **tous** les QR codes la portent, y compris pour un
client debout devant la borne. Si le tunnel tombe, plus personne ne dépose — même
sur votre Wi-Fi. Décochez la case pour revenir au réseau local le temps de le
relancer.

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

Laissez `http://localhost:8080` ouvert en plein écran, sur un appareil déclaré
**Borne**. La page affiche en permanence le QR code d'envoi et attend les photos ;
elle ne mène nulle part ailleurs.

Une barre en haut suit le parcours en **trois étapes** — Photo, Personnalisation,
Validation — pour que le client sache toujours où il en est.

Dès qu'une photo arrive, la borne bascule automatiquement dessus : l'aperçu
occupe la moitié gauche de l'écran, les choix sont numérotés à droite.

1. **Le support** — Plexiglas, Métal, Dibond, Toile, Cadre, Papier, Bois, Verre
2. **Le format** — 25×30, 30×40, 40×50, 40×60, 50×70, 20×20, 30×30, 40×40,
   50×50 cm, plus **Sur mesure** si la boutique le propose ; et l'orientation,
   portrait ou paysage, **présélectionnée d'après la photo**
3. **La forme** — Format initial, Diamant, Triangle, Cercle, plus **Libre** si la
   boutique laisse le client dessiner son contour

**Les listes suivent le support choisi** : chaque matière a ses tailles, ses
coupes et ses limites de taille propres (voir « Personnaliser la boutique »).
Changer de support recompose aussitôt les deux listes suivantes, et un choix
devenu impossible est abandonné plutôt que gardé en silence.

L'aperçu prend les proportions du format choisi, son orientation et la découpe
demandée : le client voit le tirage tel qu'il sera, recadrage compris. Un damier
très pâle montre ce que la découpe retire. Le prix s'actualise à chaque
changement, et l'orientation ne le change jamais.

> **L'orientation évite le mauvais recadrage** : une photo paysage bascule
> d'elle-même sur un cadre paysage. Un format carré n'a pas d'orientation, le
> choix disparaît alors.

> **Une matière qui ne se découpe pas** (une toile sur châssis) fait disparaître
> le menu des coupes, avec un mot d'explication. Le serveur refuse la
> combinaison même si on la force.

Ces listes sont celles livrées par défaut : chaque boutique compose les siennes
dans les **réglages**.

Avec plusieurs photos, une bande de vignettes permet de passer de l'une à
l'autre ; celles dont le tirage n'est pas encore choisi ont un contour orange.

Une **barre de commande** reste collée en bas de l'écran : la vignette du tirage
en cours, son détail, son prix, le **total du dépôt** dès qu'il y a plus d'une
photo, et trois boutons :

- **Continuer** — actif seulement quand chaque photo a son tirage ; clôture le
  dépôt, révèle le code et le QR de paiement
- **Ajouter une photo** — revient au QR code, la session reste ouverte
- **Tout annuler** — supprime les photos reçues et repart à zéro

Un bouton **Besoin d'aide ?** rappelle les trois étapes à tout moment.

### Sur le téléphone du client

Scanner le QR code ouvre la page d'envoi. Deux boutons : **Prendre une photo**
(déclenche l'appareil photo) ou **Choisir dans ma galerie**. Une fois l'envoi
terminé, la page invite à retourner à la borne.

Le téléphone doit être sur le Wi-Fi de la boutique, **sauf** si une adresse de
dépôt à distance est déclarée : le QR code porte alors une adresse publique et le
dépôt marche depuis n'importe quel réseau.

### Le paiement

Après validation, la borne affiche un second QR code, distinct de celui d'envoi.
Le client le scanne et arrive sur le récapitulatif de sa commande avec le total.
Selon les **réglages**, la page affiche en plus un lien vers votre PayPal, SumUp
ou Stripe.

**C'est le commerçant qui confirme l'encaissement**, depuis la réception, avec le
bouton « Marquer comme payé ». Le téléphone du client passe alors au vert en
direct.

> ### Pourquoi le client ne peut-il pas se déclarer payé ?
>
> Parce que l'application n'a **aucun moyen de savoir si l'argent est arrivé**.
> Le paiement se joue entre le client et son prestataire ; la borne n'est pas
> dans cette conversation. Un bouton « j'ai payé » côté client ne prouve rien —
> n'importe qui ayant le lien pourrait se marquer réglé sans payer.
>
> La confirmation appartient donc à la personne qui voit l'argent. Techniquement,
> la route d'encaissement exige le **code de retrait à 4 chiffres**, que le
> téléphone du client ne connaît jamais.
>
> **Et une confirmation automatique ?** Le mécanisme habituel — le *webhook*, où
> le prestataire appelle votre serveur — ne fonctionne pas ici : l'application
> tourne sur le réseau local d'une boutique, injoignable depuis Internet. La voie
> praticable serait que la boutique **interroge l'API du prestataire** (elle, a
> accès à Internet), au prix de saisir des identifiants API sur un poste de
> boutique. Tout se brancherait dans `_pay()` de `kiosk/server.py`, seul endroit
> qui bascule le statut.

### Sur le poste d'impression

Depuis un appareil déclaré **Imprimante** ou **PC**, trois façons d'arriver au
dépôt :

- ouvrir `http://<adresse-de-l-hôte>:8080/recuperer` et saisir le code
- cliquer sur le dépôt dans la liste **Derniers dépôts**, qui se met à jour en
  direct sans rafraîchir la page
- depuis le tableau de bord, cliquer sur une ligne des files **À encaisser** ou
  **Expirent bientôt**

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
| `SYMPS_PUBLIC_PORT` | port + 1 | port de la porte publique ; `off` pour ne pas l'ouvrir |
| `SYMPS_PUBLIC_HOST` | `127.0.0.1` | interface de la porte publique ; à ne pas élargir |
| `SYMPS_PUBLIC_URL` | — | adresse publique imposée, prioritaire sur le réglage |
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

- **Marque** — nom de la boutique et son logo.
- **Couleurs** — trois **roues chromatiques** : couleur principale, couleur
  d'accent, fond de page. Tournez la roue pour la teinte, le curseur pour la
  luminosité, ou tapez le code hexadécimal. Le reste de la palette (surfaces,
  texte, traits) s'en déduit, **y compris le passage en mode nuit** dès que le
  fond choisi est sombre : le texte s'éclaircit, la signature Symp's passe en
  blanc, et rien ne devient illisible. Cinq accords tout prêts servent de point
  de départ, et un aperçu montre le résultat avant d'enregistrer.
- **Tarification** — deux façons de fixer vos prix, avec un exemple chiffré qui
  s'actualise sous vos yeux :
  - **un prix par format**, multiplié par un **coefficient** propre à chaque
    matière (coefficient 1 = prix du format, 1,5 = moitié plus cher, 2 = double) ;
  - **un prix au m²** par matière, le tarif se calculant depuis les dimensions.
    Plus simple à tenir : un nouveau format n'a pas besoin de prix.
- **Matières** — librement créées, et **chacune se règle séparément** (voir plus
  bas) : son tarif, les tailles qu'elle propose, les coupes qu'elle accepte, son
  droit au sur-mesure et à la forme libre.
- **Formats** — librement créés : nom, largeur, hauteur. Saisissez-les en
  portrait, le client choisit lui-même portrait ou paysage.
- **Coupes** — librement créées : un nom maison (« Hublot »…), un supplément, et
  soit une géométrie toute faite, soit **une forme que vous dessinez vous-même**.
  **Une case unique supprime tout le menu** pour une boutique sans machine de
  découpe : le serveur refuse alors toute découpe, même forcée par l'API.
- **Ce que le client peut demander** — deux options que la boutique ouvre ou
  ferme : les **dimensions sur mesure** et la **forme libre** dessinée par le
  client sur la borne.
- **Encaissement** — au comptoir ou vers votre propre lien de paiement, et
  **quand** le client paie (voir plus bas).

### Chaque matière a ses propres règles

Le verre ne se coupe pas comme le papier, et ne se produit pas dans les mêmes
tailles. Le bouton au bout de chaque ligne de matière ouvre son volet :

- **les tailles proposées** — cochez celles que vous savez produire dans cette
  matière ; tout coché veut dire « toutes », y compris les formats ajoutés plus
  tard ;
- **la découpe** — cette matière se découpe ou non, et si oui, **quelles coupes**
  parmi les vôtres ;
- **le sur-mesure** — activé ou non pour cette matière, avec sa **propre limite
  de taille** (côté minimum et côté maximum en cm). Laissés vides, ces deux
  champs reprennent les limites générales de la boutique : vous ne réglez que
  les exceptions ;
- **la forme libre** — autorisée ou non pour cette matière, avec son propre
  supplément.

Les interrupteurs généraux passent avant : ce que la boutique a coupé, aucune
matière ne peut le rouvrir. Sur la borne, changer de support recompose aussitôt
la liste des tailles et des coupes, et le serveur revérifie tout à
l'enregistrement — une combinaison interdite est refusée même forcée par l'API.

### Dimensions sur mesure

Le client saisit lui-même la largeur et la hauteur. Comme il n'existe aucun prix
de grille pour des dimensions quelconques, **un tirage sur mesure est toujours
facturé au m²** de la matière, même si la boutique vend au format le reste du
temps. Les bornes de taille sont contrôlées deux fois : sur la borne pour guider
le client, et sur le serveur pour que rien ne passe en force.

### Forme libre

Le client dessine son propre contour sur la borne, par-dessus sa photo affichée
en transparence. À n'activer que si la machine sait suivre un tracé quelconque.
Le contour demande au moins trois points, et le supplément s'ajoute au prix du
tirage nu.

### Payer avant ou après

Deux enchaînements possibles après la validation, au choix de la boutique :

- **Code d'abord** (par défaut) — la borne donne le code de retrait et le QR de
  règlement ensemble. Le client paie sur son téléphone ou au comptoir, et
  récupère ses tirages dans tous les cas.
- **Paiement d'abord** — la borne affiche le **QR de règlement en grand**, et le
  code de retrait n'apparaît **qu'une fois l'encaissement confirmé**. Le
  serveur ne délivre pas le code avant : ce n'est pas qu'un affichage, une
  requête directe est refusée avec un `402`.

> Le paiement se confirme **à la réception** (voir « Le paiement »). En mode
> « paiement d'abord », un client qui règle sur son téléphone attend donc que
> quelqu'un valide l'encaissement au comptoir. C'est voulu : la borne ne sait pas
> seule qu'un virement a abouti. Le jour où l'API d'un prestataire est
> raccordée, le déblocage devient automatique — le reste du mécanisme est déjà
> en place.

### Dessiner une coupe

Choisissez la découpe « **Forme dessinée** », puis **Dessiner…**. Un éditeur
s'ouvre : cliquez pour poser un point, glissez-le pour l'ajuster, cliquez dessus
pour le retirer. Trois modèles de départ (carré, losange, étoile) évitent de
partir de zéro. Le contour se referme tout seul et s'applique tel quel sur la
borne.

Cet éditeur n'existe **que dans les réglages** : le client de la boutique, lui,
choisit seulement parmi les coupes proposées.

## Le logo de la boutique

La boutique **téléverse son logo** depuis la page Réglages (PNG, JPEG, SVG ou
WebP, 2 Mo maximum ; un fond transparent donne le meilleur résultat). Deux
places lui sont réservées :

- **dans la barre du haut**, à côté de la signature Symp's et de la mention
  « Symp's Kiosk », qui restent présentes sur toutes les pages ;
- **en grand sur l'écran d'attente de la borne**, celui que les clients voient
  le plus longtemps.

Les réglages montrent ces deux places, avec ou sans logo, dans le thème choisi.
En mode nuit, la signature Symp's passe en blanc sur fond transparent, et le
logo de la boutique reçoit une plaque claire — la plupart des logos sont dessinés
pour du papier blanc.

## Remplacer le logo Symp's

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
  server.py            serveur HTTP, routes, flux temps réel (SSE), porte publique
  storage.py           dépôts, articles, paiement, expiration
  imagemeta.py         dimensions lues dans les en-têtes (sans Pillow)
  qr.py                générateur de QR code autonome
  licence.py           abonnement : activation, licence signée, hors ligne
  postes.py            rôle de chaque appareil (borne, imprimante, PC) et droits
  tableau.py           chiffres du tableau de bord
web/
  connexion.html       abonnement de la boutique, puis rôle de cet appareil
  tableau.html         le PC : tableau de bord de la boutique
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

La colonne **Poste** dit quel rôle a le droit d'appeler la route. « — » signifie
qu'elle est ouverte à tous, y compris au téléphone du client, qui n'a pas de
rôle ; son secret est alors le jeton qu'il détient.

Une route ouverte à tous n'est pas pour autant servie **au bout du tunnel** : la
porte publique a sa propre liste blanche, plus courte, décrite dans
[Déposer depuis n'importe quel réseau](#déposer-depuis-nimporte-quel-réseau). Y
figurent seulement `/api/config`, `/api/catalogue`, `/assets/theme.css`,
`/logo-boutique`, `GET /api/sessions/<jeton>`,
`POST /api/sessions/<jeton>/images`, `/api/paiement/<jeton>`,
`/api/evenements?session=<jeton>`, `/e`, `/p` et les fichiers statiques.

| Méthode | Chemin | Poste | Rôle |
| --- | --- | --- | --- |
| `GET` `POST` `DELETE` | `/api/poste` | — | lit, déclare ou oublie le rôle de cet appareil |
| `GET` | `/api/tableau` | PC | chiffres du tableau de bord |
| `POST` | `/api/sessions` | borne | ouvre une session, renvoie le jeton et l'URL du QR |
| `GET` | `/api/sessions/<jeton>` | — | état de la session (sans le code) |
| `POST` | `/api/sessions/<jeton>/images` | — | envoie une photo (corps = octets bruts) |
| `POST` | `/api/sessions/<jeton>/images/<id>/article` | borne | choisit support, format et forme |
| `POST` | `/api/sessions/<jeton>/valider` | borne | clôture le dépôt et révèle le code |
| `GET` | `/api/sessions/<jeton>/code` | borne | le code, si le règlement est encaissé (sinon `402`) |
| `GET` | `/api/catalogue` | — | supports, formats, coupes et grille de prix |
| `GET` `POST` `DELETE` | `/api/reglages` | imprimante, PC | réglages de la boutique |
| `POST` `DELETE` | `/api/reglages/logo` | imprimante, PC | logo de la boutique |
| `GET` | `/assets/theme.css` | — | couleurs de la boutique, feuille générée |
| `GET` | `/api/paiement/<jeton>` | — | récapitulatif de la commande et son statut |
| `POST` | `/api/depots/<code>/paiement` | imprimante, PC | la réception confirme l'encaissement |
| `DELETE` | `/api/sessions/<jeton>` | borne | abandonne la session en cours |
| `GET` | `/api/depots` | imprimante, PC | liste les dépôts **validés** |
| `GET` | `/api/depots/<code>` | imprimante, PC | contenu d'un dépôt validé |
| `GET` | `/api/depots/<code>/zip` | imprimante, PC | archive du dépôt |
| `DELETE` | `/api/depots/<code>` | imprimante, PC | supprime un dépôt |
| `GET` | `/media/<id>` | — | l'image (`?dl=1` pour forcer le téléchargement) |
| `DELETE` | `/api/images/<id>` | imprimante, PC | supprime une image |
| `GET` | `/api/evenements` | — | flux SSE public (dépôts validés, suppressions) |
| `GET` | `/api/evenements?session=<jeton>` | — | flux SSE d'une seule borne |
| `GET` | `/qr.svg?d=<url>` | — | QR code en SVG |
| `GET` | `/e?s=<jeton>` | — | lien court encodé dans le QR code de la borne |
| `GET` | `/p?j=<jeton>` | — | lien court encodé dans le QR code de paiement |
| `GET` | `/r?c=<code>` | imprimante, PC | lien court vers un dépôt validé |
