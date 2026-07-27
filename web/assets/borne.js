/* La borne : affiche le QR code, montre les photos dès leur arrivée,
   puis révèle le code de retrait une fois l'opérateur satisfait. */

import {
  $, api, config, ecouterEvenements, element, estAffichable, extension,
  marquerPageActive, poids,
} from './commun.js';

const erreur = $('#message-erreur');

let reglages = null;
let session = null; // { token, images: [] }
let flux = null;
let selection = null; // identifiant de la photo affichée en grand

marquerPageActive();
demarrer();

async function demarrer() {
  try {
    reglages = await config();
    $('#retention').textContent = reglages.retention_heures;
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

/* --- étape 2 : aperçu ------------------------------------------------------ */

function afficherApercu() {
  const total = session.images.length;
  const photo = session.images.find((image) => image.id === selection) || session.images.at(-1);
  if (!photo) return montrerEtape('etape-attente');
  selection = photo.id;

  $('#titre-apercu').textContent = total > 1 ? `${total} photos reçues` : 'Photo bien reçue !';
  $('#sous-titre-apercu').textContent =
    total > 1
      ? 'Vérifiez vos photos, puis validez pour obtenir votre code de retrait.'
      : 'Vérifiez la photo, puis validez pour obtenir votre code de retrait.';

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

  $('#bande-photos').replaceChildren(...session.images.map(vignetteBande));
  $('#bande-photos').classList.toggle('cache', total < 2);
  montrerEtape('etape-apercu');
}

function vignetteBande(image) {
  const contenu = estAffichable(image.mime)
    ? element('img', { src: `/media/${image.id}`, alt: image.name, loading: 'lazy' })
    : element('span', { class: 'bande__type' }, extension(image.mime));

  return element(
    'li',
    {},
    element(
      'button',
      {
        class: `bande__vue${image.id === selection ? ' bande__vue--active' : ''}`,
        type: 'button',
        'aria-label': `Afficher ${image.name}`,
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
  if (flux) flux.close();

  const base = reglages?.url_reseau || window.location.origin;
  $('#affichage-code').textContent = depot.code;
  $('#qr-retrait').src = `/qr.svg?d=${encodeURIComponent(`${base}/r?c=${depot.code}`)}`;
  $('#lien-recuperer').href = `/recuperer?code=${depot.code}`;

  const nombre = depot.images.length;
  $('#resume-depot').textContent =
    `${nombre} ${nombre > 1 ? 'photos disponibles' : 'photo disponible'} · ` +
    `pendant ${reglages ? reglages.retention_heures : 24} h`;

  $('#galerie-finale').replaceChildren(...depot.images.map(carteImage));
  montrerEtape('etape-code');
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
      element('span', { class: 'vignette__meta' }, [
        poids(image.size) + (image.width ? ` · ${image.width}×${image.height}` : ''),
      ]),
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
