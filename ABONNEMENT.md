# Vendre Symp's Kiosk par abonnement

Ce document répond à deux questions : **comment héberger** la partie en ligne, et
**comment gérer les abonnements**. Il décrit ce qui reste à construire ; la
partie application, elle, est déjà en place.

---

## 1. Ce qui existe déjà dans l'application

L'écran de connexion et la vérification de licence sont opérationnels.

Au lancement, tant qu'aucun abonnement n'est actif, **toutes** les pages
redirigent vers `/connexion` et l'API répond `402 Paiement requis`. Seuls restent
accessibles la page de connexion, les feuilles de style et `/api/compte`.

Une fois les identifiants saisis, l'application obtient une **licence signée**
qu'elle range à côté de ses données. Ensuite :

- elle fonctionne **sans Internet** pendant `SYMPS_LICENCE_GRACE_HEURES` (72 h par
  défaut) — une coupure ne doit jamais empêcher une boutique de vendre ;
- au-delà, elle redemande confirmation au serveur ;
- si le fichier de licence est modifié à la main, la signature ne correspond plus
  et l'application se reverrouille ;
- **l'identifiant d'atelier vient du compte** : deux postes ouverts avec le même
  abonnement se trouvent sur le réseau local, et seulement eux.

### Ce que le serveur doit renvoyer

`POST /api/activer` reçoit `{email, mot_de_passe, machine}` et répond :

```json
{
  "charge": {
    "email": "photo@boutique.fr",
    "atelier": "boutique-lyon-01",
    "offre": "standard",
    "machines": 3,
    "expire_le": 1793558400.0,
    "emis_le": 1790966400.0
  },
  "signature": "<signature RSA-SHA256 de la charge, en base64>"
}
```

La signature porte sur la charge sérialisée en JSON **canonique** :
`json.dumps(charge, sort_keys=True, separators=(",", ":"))`.

`POST /api/verifier` reçoit `{atelier, machine}` et renvoie le même format : c'est
la reconfirmation périodique, qui permet de couper l'accès quand un abonnement
s'arrête.

En cas de refus, répondre un code HTTP 4xx avec `{"erreur": "message lisible"}` :
le message est affiché tel quel à l'écran.

### Les clés

Le serveur signe avec une **clé privée** ; l'application n'embarque que la **clé
publique**, qui ne permet que de vérifier. Générez la paire une fois :

```bash
openssl genrsa -out prive.pem 3072
openssl rsa -in prive.pem -pubout -out public.pem
```

`prive.pem` ne quitte jamais le serveur. `public.pem` part avec l'application.

> **Sauvegardez la clé privée.** La perdre oblige à republier l'application avec
> une nouvelle clé publique, donc à mettre à jour **toutes** les boutiques.

---

## 2. Héberger la partie en ligne

Le service à héberger est **petit** : quelques comptes, quelques abonnements, deux
routes. Il ne reçoit **aucune photo** — elles ne quittent jamais la boutique.
C'est ce qui rend l'hébergement simple et bon marché.

### Ce qu'il vous faut

1. **Un nom de domaine**, par exemple `compte.symps.fr`.
2. **Un hébergeur**. Par ordre de simplicité :
   - **une plateforme managée** (Railway, Render, Scaleway Serverless, Clever
     Cloud) : vous poussez le code, elle s'occupe du serveur, des certificats
     HTTPS et des redémarrages. C'est ce que je recommande pour commencer, de
     l'ordre de 10 à 20 € par mois.
   - **un petit serveur** (VPS Hetzner, OVH, Scaleway) à 5 € par mois : moins
     cher, mais c'est vous qui gérez les mises à jour système et les sauvegardes.
3. **Une base de données PostgreSQL** — souvent incluse chez les hébergeurs
   managés. Pour quelques centaines de boutiques, la plus petite offre suffit
   très largement.
4. **HTTPS obligatoire** : les mots de passe des clients y transitent. Les
   plateformes managées le fournissent automatiquement.
5. **Un hébergement dans l'Union européenne**, pour simplifier le RGPD.

### Ce que le service stocke

Uniquement les données de compte : e-mail, mot de passe **haché** (jamais en
clair — `argon2` ou `bcrypt`), identifiant Stripe du client, état de
l'abonnement, liste des machines activées.

Vous n'hébergez aucune photo de client final : vous n'êtes donc pas sous-traitant
au sens du RGPD pour ces images. Il vous faut malgré tout une politique de
confidentialité et un registre pour les données de compte.

---

## 3. Gérer les abonnements avec Stripe

### Mise en place, une fois pour toutes

1. Créez un compte Stripe et complétez les informations de votre société.
2. Dans **Produits**, créez « Symp's Kiosk » avec un ou plusieurs **prix
   récurrents** (mensuel, annuel), et autant d'offres que de paliers de machines.
3. Activez le **portail client** Stripe : vos clients y changent leur carte,
   téléchargent leurs factures et résilient seuls. Cela vous épargne l'essentiel
   du support de facturation.

### Le parcours d'un nouveau client

1. Il choisit une offre sur votre site.
2. Vous créez une **session Stripe Checkout** ; Stripe encaisse et gère le moyen
   de paiement. Vous ne voyez jamais le numéro de carte.
3. Stripe vous notifie par **webhook** que l'abonnement est actif.
4. Vous créez le compte et envoyez les identifiants par e-mail.
5. Le client les saisit sur la borne : elle s'active.

### Les webhooks, le point à ne pas rater

C'est Stripe qui vous dit ce qui se passe. Traitez au minimum :

| Événement | Ce que vous faites |
| --- | --- |
| `checkout.session.completed` | créer le compte, activer l'abonnement |
| `customer.subscription.updated` | changement d'offre, mettre à jour la limite de machines |
| `invoice.payment_failed` | marquer l'abonnement en impayé |
| `customer.subscription.deleted` | désactiver : les licences ne seront plus renouvelées |

> **Vérifiez toujours la signature des webhooks** (`Stripe-Signature`). Sans cela,
> n'importe qui peut vous faire croire à un paiement.

**Prévoyez de la tolérance sur les impayés.** Une carte qui expire ne doit pas
couper une boutique du jour au lendemain : Stripe réessaie plusieurs jours
(« smart retries »). Ne coupez qu'après ces relances, et prévenez par e-mail.

### Combien ça coûte

Stripe prélève environ **1,5 % + 0,25 €** par paiement européen. Sur un
abonnement à 40 € par mois, cela fait moins d'un euro.

### La durée des licences

Émettez des licences **courtes** (30 jours) et laissez l'application les
renouveler toute seule. Un abonnement résilié cesse alors de fonctionner au bout
d'un mois au maximum, sans rien avoir à faire. Des licences longues obligeraient
à un mécanisme de révocation, bien plus compliqué.

---

## 4. Ce qu'une protection par licence peut, et ne peut pas

Soyons clairs : **un contrôle de licence qui s'exécute chez le client est toujours
contournable** par quelqu'un de déterminé. C'est vrai de Topaz comme de tout le
reste. Ce que fait le nôtre :

- il empêche l'usage **accidentel** sans abonnement ;
- il rend le contournement **volontaire et technique** — donc rare chez un
  commerçant ;
- il ne peut pas être contourné en bricolant le fichier de licence, puisque la
  signature ne suivrait pas.

Ce qu'il ne fait pas : résister à quelqu'un qui modifie l'exécutable. Ne
surinvestissez pas là-dedans. Ce qui retient réellement les clients, c'est le
service — mises à jour, support, garantie de fonctionnement.

---

## 5. Le paiement des clients finaux, à ne pas confondre

Ce document parle de **votre** facturation : les boutiques qui vous paient un
abonnement. C'est un sujet distinct de l'encaissement **des clients de la
boutique**, décrit dans le README.

Retenez la différence : votre service de licences est sur Internet, donc les
webhooks Stripe y fonctionnent normalement. L'application de la boutique, elle,
tourne sur un réseau local injoignable de l'extérieur : aucun webhook ne peut
l'atteindre, et c'est pourquoi l'encaissement en boutique se confirme à la main
à la réception.

## 6. Ordre de marche conseillé

1. **Domaine + hébergeur + PostgreSQL.**
2. **Le service de licences** : comptes, mots de passe hachés, les deux routes,
   la signature. Il peut tourner sans Stripe au début, avec des comptes créés à
   la main — c'est suffisant pour vos premiers clients.
3. **Stripe** : Checkout, portail client, webhooks.
4. **L'exécutable Windows** signé (voir le README).
5. Une page de gestion pour vous : voir les boutiques, les machines, réémettre un
   mot de passe.

Vous pouvez vendre à vos premières boutiques dès l'étape 2, en créant les comptes
manuellement et en facturant hors ligne. C'est le moyen le plus rapide de valider
que le produit se vend avant d'automatiser la facturation.
