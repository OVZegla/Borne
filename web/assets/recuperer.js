/* Page de récupération : saisie du code, liste en direct, impression. */

import { brancherChangementDePoste, poserNavigation } from './navigation.js';
import {
  $, $$, api, config, ecouterEvenements, element, estAffichable, extension,
  ilYA, poids, prixLisible,
} from './commun.js';

const cases = $$('#formulaire-code input');
const messageCode = $('#message-code');
const listeDepots = $('#liste-depots');

let depotAffiche = null;

poserNavigation();
brancherChangementDePoste();

config()
  .then((valeurs) => { $('#retention').textContent = valeurs.retention_heures; })
  .catch(() => {});

/* --- saisie du code -------------------------------------------------------- */

cases.forEach((champ, index) => {
  champ.addEventListener('input', () => {
    champ.value = champ.value.replace(/\D/g, '').slice(-1);
    if (champ.value && index < cases.length - 1) cases[index + 1].focus();
    if (cases.every((c) => c.value)) valider(cases.map((c) => c.value).join(''));
  });

  champ.addEventListener('keydown', (evenement) => {
    if (evenement.key === 'Backspace' && !champ.value && index > 0) {
      cases[index - 1].focus();
      cases[index - 1].value = '';
      evenement.preventDefault();
    }
    if (evenement.key === 'ArrowLeft' && index > 0) cases[index - 1].focus();
    if (evenement.key === 'ArrowRight' && index < cases.length - 1) cases[index + 1].focus();
  });

  champ.addEventListener('paste', (evenement) => {
    const colle = (evenement.clipboardData?.getData('text') || '').replace(/\D/g, '');
    if (!colle) return;
    evenement.preventDefault();
    cases.forEach((c, i) => { c.value = colle[i] || ''; });
    if (colle.length >= cases.length) valider(colle.slice(0, cases.length));
    else cases[Math.min(colle.length, cases.length - 1)].focus();
  });
});

$('#formulaire-code').addEventListener('submit', (evenement) => evenement.preventDefault());

function reinitialiserCode() {
  cases.forEach((champ) => { champ.value = ''; });
  cases[0].focus();
}

async function valider(code) {
  messageCode.classList.add('cache');
  try {
    const depot = await api(`/api/depots/${code}`);
    afficherDepot(depot);
  } catch (echec) {
    messageCode.textContent = `Code ${code} : ${echec.message.toLowerCase()}`;
    messageCode.classList.remove('cache');
    reinitialiserCode();
  }
}

/* --- liste des dépôts ------------------------------------------------------ */

async function rafraichirListe() {
  let depots = [];
  try {
    depots = await api('/api/depots');
  } catch (echec) {
    return;
  }

  const utiles = depots.filter((depot) => depot.images.length > 0);
  $('#aucun-depot').classList.toggle('cache', utiles.length > 0);
  listeDepots.replaceChildren(...utiles.map(ligneDepot));

  if (depotAffiche) {
    const frais = depots.find((depot) => depot.code === depotAffiche.code);
    if (frais) afficherDepot(frais, { silencieux: true });
    else revenir();
  }
}

function ligneDepot(depot) {
  const apercus = depot.images
    .filter((image) => estAffichable(image.mime))
    .slice(0, 4)
    .map((image) => element('img', { src: `/media/${image.id}`, alt: '', loading: 'lazy' }));

  const nombre = depot.images.length;
  return element(
    'li',
    {},
    element('button', { class: 'depot', type: 'button', onclick: () => afficherDepot(depot) }, [
      element('span', { class: 'depot__code' }, depot.code),
      element('span', { class: 'depot__infos' }, [
        element(
          'span',
          { class: 'depot__titre' },
          `${nombre} ${nombre > 1 ? 'tirages' : 'tirage'} · ${prixLisible(depot.total, depot.devise)}`,
        ),
        element('span', { class: 'depot__meta' }, `validé ${ilYA(depot.validated_at || depot.created_at)}`),
      ]),
      badgePaiement(depot),
      element('span', { class: 'depot__apercus' }, apercus),
    ]),
  );
}

function badgePaiement(depot) {
  const paye = depot.paiement === 'paye';
  return element('span', { class: `etat ${paye ? 'etat--paye' : 'etat--attente'}` }, [
    element('span', { class: 'etat__point' }),
    paye ? ' Payé' : ' En attente',
  ]);
}

/* --- contenu d'un dépôt ---------------------------------------------------- */

function afficherDepot(depot, options = {}) {
  depotAffiche = depot;

  $('#titre-code').textContent = depot.code;
  const nombre = depot.images.length;
  $('#resume-contenu').textContent =
    `${nombre} ${nombre > 1 ? 'tirages' : 'tirage'} · ` +
    `${prixLisible(depot.total, depot.devise)} · validé ${ilYA(depot.validated_at || depot.created_at)}`;
  $('#etat-depot').replaceChildren(badgePaiement(depot));
  // L'encaissement se confirme ici, par la personne qui voit l'argent.
  $('#btn-encaisser').classList.toggle('cache', depot.paiement === 'paye');
  $('#btn-zip').href = `/api/depots/${depot.code}/zip`;
  $('#btn-zip').classList.toggle('cache', nombre === 0);

  $('#galerie').replaceChildren(...depot.images.map(carteImage));
  $('#etape-code').classList.add('cache');
  $('#etape-contenu').classList.remove('cache');

  if (!options.silencieux) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const url = new URL(window.location);
    url.searchParams.set('code', depot.code);
    window.history.replaceState({}, '', url);
  }
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

  const actions = [
    element(
      'a',
      { class: 'bouton bouton--secondaire', href: `/media/${image.id}?dl=1`, download: image.name },
      'Télécharger',
    ),
  ];

  // L'impression navigateur n'a de sens que pour ce que la page sait afficher.
  if (estAffichable(image.mime)) {
    actions.unshift(
      element(
        'a',
        { class: 'bouton bouton--principal', href: `/impression?image=${image.id}` },
        'Imprimer',
      ),
    );
  }

  return element('li', { class: 'vignette' }, [
    apercu,
    element('div', { class: 'vignette__corps' }, [
      element('span', { class: 'vignette__nom', title: image.name }, image.name),
      image.article
        ? element('span', { class: 'vignette__tirage' }, image.article.libelle)
        : null,
      element(
        'span',
        { class: 'vignette__meta' },
        image.article
          ? prixLisible(image.article.prix, '€')
          : poids(image.size) + (image.width ? ` · ${image.width}×${image.height}` : ''),
      ),
    ]),
    element('div', { class: 'vignette__actions' }, actions),
  ]);
}

function revenir() {
  depotAffiche = null;
  $('#etape-contenu').classList.add('cache');
  $('#etape-code').classList.remove('cache');
  reinitialiserCode();
  const url = new URL(window.location);
  url.searchParams.delete('code');
  window.history.replaceState({}, '', url);
}

$('#btn-encaisser').addEventListener('click', async () => {
  if (!depotAffiche) return;
  const total = prixLisible(depotAffiche.total, depotAffiche.devise);
  if (!window.confirm(`Confirmer l'encaissement de ${total} pour le dépôt ${depotAffiche.code} ?`)) {
    return;
  }
  try {
    await api(`/api/depots/${depotAffiche.code}/paiement`, { method: 'POST' });
    await rafraichirListe();
  } catch (echec) {
    window.alert(`Encaissement impossible : ${echec.message}`);
  }
});

$('#btn-retour').addEventListener('click', revenir);

$('#btn-supprimer').addEventListener('click', async () => {
  if (!depotAffiche) return;
  const question = `Supprimer définitivement le dépôt ${depotAffiche.code} et ses images ?`;
  if (!window.confirm(question)) return;
  try {
    await api(`/api/depots/${depotAffiche.code}`, { method: 'DELETE' });
    revenir();
    rafraichirListe();
  } catch (echec) {
    window.alert(`Suppression impossible : ${echec.message}`);
  }
});

/* --- démarrage ------------------------------------------------------------- */

ecouterEvenements({
  image: rafraichirListe,
  depot: rafraichirListe,
  paiement: rafraichirListe,
  suppression: rafraichirListe,
  purge: rafraichirListe,
});

rafraichirListe().then(() => {
  const demande = new URLSearchParams(window.location.search).get('code');
  if (demande && /^\d+$/.test(demande)) valider(demande);
  else cases[0].focus();
});
