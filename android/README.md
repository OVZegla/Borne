# La borne sur tablette Android

Une application qui ne contient **aucune interface** : elle trouve la machine
hôte sur le réseau local, affiche sa page en plein écran, et y revient toute
seule quand le réseau a hoqueté. Tout ce que voit le client vient du serveur de
la boutique — l'application n'est qu'une vitre.

C'est ce qui permet de sortir la tablette du carton, la poser sur le Wi-Fi de la
boutique, et l'allumer. **Rien à saisir**, pas même une adresse.

---

## Ce que fait l'application

1. **Elle cherche l'hôte.** Diffusion UDP sur le port 8079, exactement le
   dialogue de `kiosk/reseau.py` :

   ```
   borne  -->  diffusion   SYMPS?1 <atelier>
   hôte   -->  réponse     SYMPS!1 {"host": "...", "port": 8080, ...}
   ```

   L'adresse retenue est celle **vue par le réseau**, pas celle que l'hôte
   déclare : elle reste juste même si la machine a plusieurs interfaces.

2. **Elle retient l'hôte trouvé.** Au rallumage du matin, elle repart dessus
   directement et ne rediffuse une recherche que s'il ne répond plus. Le
   démarrage est donc immédiat en usage courant.

3. **Elle affiche sa page**, sans barre de statut ni barre de navigation, écran
   maintenu allumé, retour arrière neutralisé.

Le rôle « borne » se choisit **une seule fois**, en tapant sur *Borne* au premier
démarrage : le serveur pose un cookie d'un an que l'application conserve.

L'application ne demande que deux permissions — `INTERNET` et
`ACCESS_NETWORK_STATE`. Ni caméra, ni stockage, ni localisation : c'est le
téléphone du client qui prend les photos, jamais la borne.

## Construire l'APK

Le projet n'a **aucune dépendance** : ni AndroidX, ni bibliothèque tierce. Il
tient dans une WebView et un socket UDP.

### Avec Android Studio (le plus simple)

1. *File → Open* → choisir ce dossier `android/`.
2. Laisser Android Studio installer le SDK qu'il réclame.
3. *Build → Generate Signed App Bundle / APK* → **APK** → créer une clé de
   signature et la **garder précieusement** : sans elle, vous ne pourrez plus
   publier de mise à jour de cette application.

### En ligne de commande

Il faut le SDK Android installé et `ANDROID_HOME` renseigné :

```bash
cd android
./gradlew assembleRelease
```

L'APK sort dans `app/build/outputs/apk/release/`.

## Installer sur la tablette

Par câble, avec `adb` :

```bash
adb install -r app/build/outputs/apk/release/app-release.apk
```

Ou en copiant l'APK sur la tablette et en l'ouvrant, après avoir autorisé les
sources inconnues.

## Verrouiller la tablette

Une borne en magasin ne doit pas pouvoir être quittée par un client.

**Sans rien configurer**, l'application est déjà en plein écran, sans barres, et
le retour arrière ne la quitte pas. Elle demande l'épinglage d'écran, qu'Android
fait confirmer une fois.

**Verrouillage complet**, sans aucune confirmation : faites de l'application le
*propriétaire de l'appareil*. Sur une tablette **neuve ou réinitialisée**, sans
aucun compte Google configuré :

```bash
adb shell dpm set-device-owner fr.symps.borne/.MainActivity
```

L'épinglage devient alors silencieux et le client ne peut plus sortir de
l'application. Cette commande est à passer **une fois, à la préparation de la
tablette** — jamais en boutique.

> Le propriétaire d'appareil ne se retire qu'en réinitialisant la tablette.
> Préparez-en une avant de figer votre procédure.

## Ce qui est vérifié, et ce qui ne l'est pas

Soyons précis, parce que la différence compte :

**Vérifié pour de vrai.** `Decouverte.kt` a été compilé avec `kotlinc` 1.9.24 et
exécuté sur la JVM **contre le vrai serveur Python** : il trouve l'hôte, lit le
bon port, retient l'adresse vue par le réseau, et ignore un atelier qui n'est pas
le sien. C'est la partie qui portait le vrai risque, et elle marche.

**Non vérifié.** L'APK n'a jamais été compilé ni installé sur un appareil :
l'environnement où ce code a été écrit n'a pas accès au SDK Android. `MainActivity.kt`
et la configuration Gradle sont écrits avec soin mais **n'ont pas tourné**.
Attendez-vous à un ou deux ajustements au premier build — une version de plugin à
accepter, un avertissement de lint à lever. Rien de structurel.

## Ce qui reste à décider

- **L'orientation.** Elle est libre aujourd'hui. Une borne est en général fixée
  dans un sens : ajoutez `android:screenOrientation="landscape"` (ou `portrait`)
  à l'activité dans `AndroidManifest.xml`.
- **L'atelier.** L'application cherche sans filtre, ce qui convient à une
  boutique seule sur son réseau. La préférence `atelier` est déjà lue par
  `MainActivity` ; c'est là que se branchera l'identifiant du compte abonné, le
  jour où deux boutiques partageront un réseau.
- **Les mises à jour.** Rien n'est prévu : l'APK se réinstalle à la main. Pour un
  parc de bornes, il faudra soit un magasin privé, soit un serveur de mise à jour.
