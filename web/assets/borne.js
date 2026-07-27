/* La borne : affiche le QR code, montre les photos dès leur arrivée,
   puis révèle le code de retrait une fois l'opérateur satisfait. */

import {
  $, api, catalogue, config, ecouterEvenements, element, estAffichable, extension,
  marquerPageActive, poids, prixLisible,
} from './commun.js';

const erreur = $('#message-erreur');

let reglages = null;
let cat = null; // catalogue : matières, formats, formes, grille de prix
let session = null; // { token, images: [] }
let flux = null;
let selection = null; // identifiant de la photo affichée en grand
let brouillon = { matiere: null, format: null, forme: 'initial' };

marquerPageActive();
demarrer();

async function demarrer() {
  try {
    [reglages, cat] = await Promise.all([config(), catalogue()]);
    $('#retention').textContent = reglages.retention_heures;
    construireOptions();
  } catch (echec) {
    return afficherErreur('Impossible de contacter la borne. Le serveur tourne-t-il toujours ?');
  }

  try {
    const ouverte = await api('/api/sessions', { method: 'POST' });
    session = { token: ouverte.token, images: [] };
    $('#image-qr').src = `/qr.svg?d=${encodeURIComponent(ouverte.url_envoi)}`;
    $('#url-envoi').textContent = ouverte.url_envoi;
    brancherFlux();
  } catch (echec) {
    afficherErreur(`Impossible d'ouvrir une session : ${echec.message}`);
  }
}

/* --- temps réel ------------------------------------------------------------ */

function brancherFlux() {
  if (flux) flux.close();
  flux = ecouterEvenements(
    {
      image: (donnees) => {
        if (!donnees?.image) return;
        session.images.push(donnees.image);
        selection = donnees.image.id;
        afficherApercu();
      },
      paiement: (donnees) => marquerPaye(donnees?.paiement === 'paye'),
      suppression: rafraichirSession,
      purge: rafraichirSession,
    },
    session.token,
  );
}

async function rafraichirSession() {
  if (!session) return;
  try {
    const fraiche = await api(`/api/sessions/${session.token}`);
    session.images = fraiche.images;
    if (!session.images.some((image) => image.id === selection)) {
      selection = session.images.at(-1)?.id ?? null;
    }
    if (session.images.length) afficherApercu();
    else montrerEtape('etape-attente');
  } catch (echec) {
    // La session a disparu (expirée ou purgée) : on repart de zéro.
    window.location.reload();
  }
}

/* --- étape 2 : choix du tirage --------------------------------------------- */

function construireOptions() {
  $('#liste-matieres').replaceChildren(
    ...cat.matieres.map((m) =>
      pastilleChoix(m.nom, () => {
        brouillon.matiere = m.cle;
        if (!m.formes) brouillon.forme = 'initial';
        appliquerChoix();
      }, () => brouillon.matiere === m.cle),
    ),
  );

  $('#liste-formats').replaceChildren(
    ...cat.formats.map((f) =>
      pastilleChoix(f.nom, () => {
        brouillon.format = f.cle;
        appliquerChoix();
      }, () => brouillon.format === f.cle),
    ),
  );

  $('#liste-formes').replaceChildren(
    ...cat.formes.map((f) =>
      pastilleChoix(f.nom, () => {
        brouillon.forme = f.cle;
        appliquerChoix();
      }, () => brouillon.forme === f.cle, `forme-${f.cle}`),
    ),
  );
}

function pastilleChoix(libelle, auClic, estActif, classeSup = '') {
  return element(
    'button',
    {
      class: `pastille-choix ${classeSup}`.trim(),
      type: 'button',
      dataset: { actif: String(estActif()) },
      onclick: auClic,
    },
    libelle,
  );
}

/** Répercute le brouillon sur les pastilles, l'aperçu, le prix et le serveur. */
function appliquerChoix(enregistrer = true) {
  const matiere = cat.matieres.find((m) => m.cle === brouillon.matiere);
  const formesPermises = !matiere || matiere.formes;

  // Une matière sans découpe (la toile) fige la forme sur « format initial ».
  $('#bloc-formes').classList.toggle('choix--verrouille', !formesPermises);
  $('#note-forme').classList.toggle('cache', formesPermises);
  for (const bouton of $('#liste-formes').children) {
    const estInitial = bouton.classList.contains('forme-initial');
    bouton.disabled = !formesPermises && !estInitial;
  }

  rafraichirPastilles();
  majApercu();

  const complet = brouillon.matiere && brouillon.format && brouillon.forme;
  const montant = complet
    ? cat.prix[`${brouillon.matiere}|${brouillon.format}|${brouillon.forme}`]
    : null;
  $('#prix-article').textContent =
    montant === null || montant === undefined ? '—' : prixLisible(montant, cat.devise);

  if (complet && enregistrer) enregistrerArticle();
  majRecapitulatif();
}

function rafraichirPastilles() {
  const groupes = [
    ['#liste-matieres', cat.matieres, 'matiere'],
    ['#liste-formats', cat.formats, 'format'],
    ['#liste-formes', cat.formes, 'forme'],
  ];
  for (const [selecteur, entrees, champ] of groupes) {
    [...$(selecteur).children].forEach((bouton, index) => {
      bouton.dataset.actif = String(entrees[index].cle === brouillon[champ]);
    });
  }
}

/** L'aperçu montre le vrai rapport hauteur/largeur et la vraie découpe. */
function majApercu() {
  const rendu = $('#rendu');
  const format = cat.formats.find((f) => f.cle === brouillon.format);
  rendu.style.aspectRatio = format ? `${format.largeur} / ${format.hauteur}` : '';
  rendu.dataset.forme = brouillon.forme || 'initial';
  rendu.classList.toggle('rendu--cadre', brouillon.matiere === 'cadre');
}

async function enregistrerArticle() {
  const photo = session.images.find((image) => image.id === selection);
  if (!photo) return;
  try {
    const maj = await api(`/api/sessions/${session.token}/images/${photo.id}/article`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(brouillon),
    });
    Object.assign(photo, maj);
    majRecapitulatif();
    $('#bande-photos').replaceChildren(...session.images.map(vignetteBande));
  } catch (echec) {
    afficherErreur(`Choix impossible : ${echec.message}`);
  }
}

function majRecapitulatif() {
  const configurees = session.images.filter((image) => image.article);
  const total = configurees.reduce((somme, image) => somme + image.article.prix, 0);
  const manquantes = session.images.length - configurees.length;

  const lignes = configurees.map((image) =>
    element('li', { class: 'recap__ligne' }, [
      element('span', { class: 'recap__nom' }, image.name),
      element('span', { class: 'recap__detail' }, image.article.libelle),
      element('span', { class: 'recap__prix' }, prixLisible(image.article.prix, cat.devise)),
    ]),
  );

  const contenu = [];
  if (lignes.length) {
    contenu.push(element('ul', { class: 'recap__liste' }, lignes));
    contenu.push(
      element('p', { class: 'total' }, [
        element('span', {}, 'Total'),
        element('strong', {}, prixLisible(total, cat.devise)),
      ]),
    );
  }
  if (manquantes > 0) {
    contenu.push(
      element(
        'p',
        { class: 'recap__reste' },
        manquantes > 1
          ? `${manquantes} photos n'ont pas encore de tirage choisi.`
          : "Il reste 1 photo sans tirage choisi.",
      ),
    );
  }
  $('#recap-commande').replaceChildren(...contenu);

  const pret = session.images.length > 0 && manquantes === 0;
  $('#btn-valider').disabled = !pret;
}

function afficherApercu() {
  const total = session.images.length;
  const photo = session.images.find((image) => image.id === selection) || session.images.at(-1);
  if (!photo) return montrerEtape('etape-attente');
  selection = photo.id;

  $('#titre-apercu').textContent = total > 1 ? `${total} photos reçues` : 'Photo bien reçue !';
  $('#sous-titre-apercu').textContent =
    'Choisissez la matière, les dimensions et la forme de chaque tirage.';

  const geante = $('#photo-geante');
  if (estAffichable(photo.mime)) {
    geante.src = `/media/${photo.id}`;
    geante.alt = photo.name;
    geante.classList.remove('cache');
  } else {
    geante.classList.add('cache');
  }

  $('#legende-photo').textContent = [
    photo.name,
    poids(photo.size),
    photo.width ? `${photo.width} × ${photo.height} px` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  // On reprend le tirage déjà choisi pour cette photo, sinon on repart à vide.
  brouillon = photo.article
    ? { matiere: photo.article.matiere, format: photo.article.format, forme: photo.article.forme }
    : { matiere: null, format: null, forme: 'initial' };
  appliquerChoix(false);

  $('#bande-photos').replaceChildren(...session.images.map(vignetteBande));
  $('#bande-photos').classList.toggle('cache', total < 2);
  montrerEtape('etape-apercu');
}

function vignetteBande(image) {
  const contenu = estAffichable(image.mime)
    ? element('img', { src: `/media/${image.id}`, alt: image.name, loading: 'lazy' })
    : element('span', { class: 'bande__type' }, extension(image.mime));

  const classes = [
    'bande__vue',
    image.id === selection ? 'bande__vue--active' : '',
    image.article ? 'bande__vue--prete' : 'bande__vue--incomplete',
  ]
    .filter(Boolean)
    .join(' ');

  return element(
    'li',
    {},
    element(
      'button',
      {
        class: classes,
        type: 'button',
        'aria-label': `${image.article ? 'Modifier' : 'Choisir'} le tirage de ${image.name}`,
        onclick: () => {
          selection = image.id;
          afficherApercu();
        },
      },
      contenu,
    ),
  );
}

/* --- actions --------------------------------------------------------------- */

$('#btn-ajouter').addEventListener('click', () => {
  // On revient au QR code : la session reste la même, le téléphone peut renvoyer.
  montrerEtape('etape-attente');
});

$('#btn-annuler').addEventListener('click', async () => {
  if (!window.confirm('Annuler ce dépôt et supprimer les photos reçues ?')) return;
  try {
    await api(`/api/sessions/${session.token}`, { method: 'DELETE' });
  } catch (echec) {
    /* la session avait peut-être déjà disparu */
  }
  window.location.reload();
});

$('#btn-valider').addEventListener('click', async () => {
  const bouton = $('#btn-valider');
  bouton.disabled = true;
  try {
    const validee = await api(`/api/sessions/${session.token}/valider`, { method: 'POST' });
    afficherCode(validee);
  } catch (echec) {
    afficherErreur(`Validation impossible : ${echec.message}`);
    bouton.disabled = false;
  }
});

$('#btn-recommencer').addEventListener('click', () => window.location.reload());

/* --- étape 3 : le code ----------------------------------------------------- */

function afficherCode(depot) {
  $('#affichage-code').textContent = depot.code;
  $('#qr-paiement').src = `/qr.svg?d=${encodeURIComponent(depot.url_paiement)}`;
  $('#lien-recuperer').href = `/recuperer?code=${depot.code}`;
  $('#total-commande').textContent = prixLisible(depot.total, depot.devise);

  const nombre = depot.images.length;
  $('#resume-depot').textContent =
    `${nombre} ${nombre > 1 ? 'tirages commandés' : 'tirage commandé'} · ` +
    `disponibles ${reglages ? reglages.retention_heures : 24} h`;

  $('#galerie-finale').replaceChildren(...depot.images.map(carteImage));
  marquerPaye(depot.paiement === 'paye');
  montrerEtape('etape-code');
  // Le flux de la session reste ouvert : c'est lui qui apportera le paiement.
}

function marquerPaye(paye) {
  const etat = $('#etat-paiement');
  etat.className = `etat ${paye ? 'etat--paye' : 'etat--attente'}`;
  etat.replaceChildren(
    element('span', { class: 'etat__point' }),
    document.createTextNode(paye ? ' Paiement reçu' : ' Paiement en attente'),
  );
  $('#qr-paiement').classList.toggle('qr--regle', paye);
}

function carteImage(image) {
  const apercu = estAffichable(image.mime)
    ? element('img', {
        class: 'vignette__image',
        src: `/media/${image.id}`,
        alt: image.name,
        loading: 'lazy',
      })
    : element('div', { class: 'vignette__vide' }, extension(image.mime));

  return element('li', { class: 'vignette' }, [
    apercu,
    element('div', { class: 'vignette__corps' }, [
      element('span', { class: 'vignette__nom', title: image.name }, image.name),
      element(
        'span',
        { class: 'vignette__meta' },
        image.article
          ? `${image.article.libelle} · ${prixLisible(image.article.prix, cat.devise)}`
          : poids(image.size),
      ),
    ]),
  ]);
}

/* --- utilitaires ----------------------------------------------------------- */

function montrerEtape(identifiant) {
  for (const nom of ['etape-attente', 'etape-apercu', 'etape-code']) {
    $(`#${nom}`).classList.toggle('cache', nom !== identifiant);
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function afficherErreur(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
}
