/* La borne : QR d'envoi, personnalisation du tirage, code de retrait. */

import {
  $, api, catalogue, config, ecouterEvenements, element, estAffichable, extension,
  poids, prixLisible,
} from './commun.js';

const SUR_MESURE = '__sur_mesure__';
const FORME_LIBRE = '__libre__';

const erreur = $('#message-erreur');

let reglages = null;
let cat = null;
let session = null;
let flux = null;
let selection = null;
let brouillon = vide();

demarrer();

function vide() {
  return {
    matiere: null, format: null, forme: null,
    orientation: 'portrait', mesures: null, points: null,
  };
}

async function demarrer() {
  try {
    [reglages, cat] = await Promise.all([config(), catalogue()]);
    construireOptions();
  } catch (echec) {
    return afficherErreur('Impossible de contacter la borne. Le serveur tourne-t-il toujours ?');
  }

  try {
    const ouverte = await api('/api/sessions', { method: 'POST' });
    session = { token: ouverte.token, images: [] };
    $('#image-qr').src = `/qr.svg?d=${encodeURIComponent(ouverte.url_envoi)}`;
    brancherFlux();
  } catch (echec) {
    afficherErreur(`Impossible d'ouvrir une session : ${echec.message}`);
  }
  montrerEtape('etape-attente');
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
    window.location.reload();
  }
}

/* --- icônes ---------------------------------------------------------------- */

const CONTOURS = {
  rectangle: 'M6 12h36v24H6z',
  cercle: 'M24 6a18 18 0 1 0 .01 0z',
  losange: 'M24 4 44 24 24 44 4 24z',
  triangle: 'M24 6 44 42H4z',
  hexagone: 'M24 4l17 10v20L24 44 7 34V14z',
  arche: 'M9 42V22a15 15 0 0 1 30 0v20z',
  personnalise: 'M14 10c8-6 20-4 22 5s-6 10-4 17-10 12-18 7S4 20 14 10z',
};

function iconeForme(geometrie) {
  const chemin = CONTOURS[geometrie] || CONTOURS.rectangle;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 48 48');
  svg.setAttribute('class', 'carte-choix__forme');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', chemin);
  svg.append(path);
  return svg;
}

/** Carte sélectionnable : une vignette, un nom, une pastille de sélection. */
function carteChoix({ cle, visuel = null, nom, actif, auClic, classe = '' }) {
  const coche = element('span', { class: 'carte-choix__coche', 'aria-hidden': 'true' }, '✓');
  return element(
    'button',
    {
      class: `carte-choix ${classe}`.trim(),
      type: 'button',
      dataset: { cle, actif: String(actif) },
      onclick: auClic,
    },
    [visuel, element('span', { class: 'carte-choix__nom' }, nom), coche],
  );
}

/* --- ce que la matière choisie autorise ------------------------------------- */

/* Tout est réglable matière par matière : les formats proposés, les coupes, le
   droit au sur-mesure et ses limites, la forme libre. Le serveur a déjà résolu
   l'héritage boutique → matière ; on lit simplement les listes reçues. */

function matiereCourante() {
  return cat.matieres.find((m) => m.cle === brouillon.matiere) || null;
}

/** Avant qu'un support soit choisi, on montre toute l'offre de la boutique. */
function formatsOfferts() {
  const matiere = matiereCourante();
  return matiere ? cat.formats.filter((f) => matiere.formats.includes(f.cle)) : cat.formats;
}

function formesOffertes() {
  const matiere = matiereCourante();
  return matiere ? cat.formes.filter((f) => matiere.formes.includes(f.cle)) : cat.formes;
}

function reglageMesure() {
  return matiereCourante()?.sur_mesure || { actif: false, min_cm: 10, max_cm: 120 };
}

function reglageLibre() {
  return matiereCourante()?.forme_libre || { actif: false, supplement: 0 };
}

function formeNeutre() {
  const offertes = formesOffertes();
  return (offertes.find((f) => f.geometrie === 'rectangle') || offertes[0])?.cle ?? null;
}

/* --- construction des choix ------------------------------------------------ */

function construireOptions() {
  // Supports
  $('#liste-matieres').replaceChildren(
    ...cat.matieres.map((m) =>
      carteChoix({
        cle: m.cle,
        nom: m.nom,
        classe: 'carte-choix--support',
        actif: brouillon.matiere === m.cle,
        auClic: () => choisirMatiere(m.cle),
      }),
    ),
  );

  // Orientation, en bascule segmentée
  $('#liste-orientations').replaceChildren(
    ...[
      ['portrait', 'Portrait', 'M17 4h14v24H17z'],
      ['paysage', 'Paysage', 'M6 10h24v14H6z'],
    ].map(([cle, nom, chemin]) => {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 36 32');
      svg.setAttribute('aria-hidden', 'true');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', chemin);
      svg.append(path);
      return element(
        'button',
        {
          class: `segment orientation-${cle}`,
          type: 'button',
          dataset: { cle, actif: String(brouillon.orientation === cle) },
          onclick: () => { brouillon.orientation = cle; appliquerChoix(); },
        },
        [svg, element('span', {}, nom)],
      );
    }),
  );

  for (const id of ['#mesure-largeur', '#mesure-hauteur']) {
    $(id).addEventListener('input', () => {
      brouillon.mesures = [Number($('#mesure-largeur').value), Number($('#mesure-hauteur').value)];
      appliquerChoix();
    });
  }

  construireFormats();
  construireFormes();
}

/** Un support n'a pas les mêmes tailles qu'un autre : la liste se refait. */
function construireFormats() {
  const pastilles = formatsOfferts().map((f) =>
    element(
      'button',
      {
        class: 'pastille-format',
        type: 'button',
        dataset: { cle: f.cle, actif: String(brouillon.format === f.cle) },
        onclick: () => { brouillon.format = f.cle; brouillon.mesures = null; appliquerChoix(); },
      },
      f.nom,
    ),
  );

  const mesure = reglageMesure();
  if (mesure.actif) {
    pastilles.push(
      element(
        'button',
        {
          class: 'pastille-format pastille-format--mesure',
          type: 'button',
          dataset: { cle: SUR_MESURE, actif: String(brouillon.format === SUR_MESURE) },
          onclick: () => {
            brouillon.format = SUR_MESURE;
            const milieu = Math.round((mesure.min_cm + mesure.max_cm) / 4) * 2;
            brouillon.mesures = brouillon.mesures || [milieu, milieu];
            $('#mesure-largeur').value = brouillon.mesures[0];
            $('#mesure-hauteur').value = brouillon.mesures[1];
            appliquerChoix();
          },
        },
        [element('span', { 'aria-hidden': 'true' }, '⤢'), ' Sur mesure'],
      ),
    );
    $('#aide-sur-mesure').textContent =
      `Entre ${mesure.min_cm} et ${mesure.max_cm} cm de côté`
      + `${matiereCourante() ? ` en ${matiereCourante().nom.toLowerCase()}` : ''}.`;
    for (const id of ['#mesure-largeur', '#mesure-hauteur']) {
      $(id).min = mesure.min_cm;
      $(id).max = mesure.max_cm;
    }
  }
  $('#liste-formats').replaceChildren(...pastilles);
}

function construireFormes() {
  const offertes = formesOffertes();
  const cartes = offertes.map((f) =>
    carteChoix({
      cle: f.cle,
      visuel: iconeForme(f.geometrie),
      nom: f.nom,
      actif: brouillon.forme === f.cle,
      classe: `forme-${f.geometrie}`,
      auClic: () => { brouillon.forme = f.cle; brouillon.points = null; appliquerChoix(); },
    }),
  );

  if (reglageLibre().actif) {
    cartes.push(
      carteChoix({
        cle: FORME_LIBRE,
        visuel: iconeForme('personnalise'),
        nom: 'Libre',
        actif: brouillon.forme === FORME_LIBRE,
        classe: 'forme-libre',
        auClic: ouvrirEditeurForme,
      }),
    );
  }
  $('#liste-formes').replaceChildren(...cartes);

  // Un seul choix possible n'est pas un choix : le bloc disparaît.
  $('#bloc-formes').classList.toggle('cache', cartes.length < 2);

  const matiere = matiereCourante();
  const bridee = Boolean(matiere) && cartes.length < 2;
  $('#note-forme').classList.toggle('cache', !bridee);
  if (bridee) {
    $('#note-forme').textContent =
      `${matiere.nom} ne se découpe pas : le tirage garde ses angles droits.`;
  }
}

/** Changer de support peut invalider le format ou la coupe déjà choisis. */
function choisirMatiere(cle) {
  brouillon.matiere = cle;

  if (brouillon.format === SUR_MESURE) {
    if (!reglageMesure().actif) { brouillon.format = null; brouillon.mesures = null; }
  } else if (brouillon.format && !formatsOfferts().some((f) => f.cle === brouillon.format)) {
    brouillon.format = null;
  }

  if (brouillon.forme === FORME_LIBRE) {
    if (!reglageLibre().actif) { brouillon.forme = formeNeutre(); brouillon.points = null; }
  } else if (!formesOffertes().some((f) => f.cle === brouillon.forme)) {
    brouillon.forme = formeNeutre();
  }

  construireFormats();
  construireFormes();
  appliquerChoix();
}

function orientationNaturelle(photo) {
  if (!photo?.width || !photo?.height) return 'portrait';
  return photo.width > photo.height ? 'paysage' : 'portrait';
}

function formatCourant() {
  return cat.formats.find((f) => f.cle === brouillon.format);
}

function dimensionsCourantes() {
  if (brouillon.format === SUR_MESURE) return brouillon.mesures || [0, 0];
  const format = formatCourant();
  return format ? [format.largeur, format.hauteur] : [0, 0];
}

/* --- application d'un choix ------------------------------------------------ */

function appliquerChoix(enregistrer = true) {
  const [largeur, hauteur] = dimensionsCourantes();
  const carre = largeur === hauteur && largeur > 0;
  $('#liste-orientations').classList.toggle('cache', carre || !brouillon.format);
  if (carre) brouillon.orientation = 'portrait';

  $('#bloc-sur-mesure').classList.toggle('cache', brouillon.format !== SUR_MESURE);

  rafraichirSelections();
  majApercu();
  majSommaire();

  if (estComplet() && enregistrer) enregistrerArticle();
}

function estComplet() {
  if (!brouillon.matiere || !brouillon.format || !brouillon.forme) return false;
  if (brouillon.format === SUR_MESURE) {
    const [l, h] = brouillon.mesures || [0, 0];
    const { min_cm: mini, max_cm: maxi } = reglageMesure();
    if (!(l >= mini && l <= maxi && h >= mini && h <= maxi)) return false;
  }
  if (brouillon.forme === FORME_LIBRE && !(brouillon.points?.length >= 3)) return false;
  return true;
}

function rafraichirSelections() {
  const attendu = {
    '#liste-matieres': brouillon.matiere,
    '#liste-orientations': brouillon.orientation,
    '#liste-formats': brouillon.format,
    '#liste-formes': brouillon.forme,
  };
  for (const [selecteur, choisi] of Object.entries(attendu)) {
    for (const bouton of $(selecteur).children) {
      bouton.dataset.actif = String(bouton.dataset.cle === choisi);
    }
  }
}

function prixCourant() {
  if (!estComplet()) return null;
  const matiere = matiereCourante();

  if (brouillon.format === SUR_MESURE) {
    const [l, h] = brouillon.mesures;
    return arrondi((l / 100) * (h / 100) * (matiere?.prix_m2 || 0) + supplementCourant());
  }
  if (brouillon.forme === FORME_LIBRE) {
    // Le tarif nu se lit sur la coupe rectangulaire, dont on retire le supplément.
    const neutre = cat.formes.find((f) => f.cle === formeNeutre());
    const cle = `${brouillon.matiere}|${brouillon.format}|${neutre?.cle}`;
    return arrondi((cat.prix[cle] ?? 0) - (neutre?.supplement || 0) + supplementCourant());
  }
  return cat.prix[`${brouillon.matiere}|${brouillon.format}|${brouillon.forme}`] ?? null;
}

function supplementCourant() {
  return brouillon.forme === FORME_LIBRE ? (reglageLibre().supplement || 0) : 0;
}

function arrondi(valeur) {
  return Math.round(valeur * 100) / 100;
}

/* --- aperçu ---------------------------------------------------------------- */

function majApercu() {
  const rendu = $('#rendu');
  const [largeur, hauteur] = dimensionsCourantes();
  if (largeur > 0 && hauteur > 0) {
    const paysage = brouillon.orientation === 'paysage' && largeur !== hauteur;
    const [l, h] = paysage ? [hauteur, largeur] : [largeur, hauteur];
    rendu.style.aspectRatio = `${l} / ${h}`;
  } else {
    rendu.style.aspectRatio = '';
  }

  if (brouillon.forme === FORME_LIBRE && brouillon.points?.length >= 3) {
    rendu.dataset.forme = 'personnalise';
    rendu.style.clipPath = polygone(brouillon.points);
    return;
  }

  const forme = cat.formes.find((f) => f.cle === brouillon.forme);
  rendu.dataset.forme = forme ? forme.geometrie : 'rectangle';
  rendu.style.clipPath =
    forme?.geometrie === 'personnalise' && forme.points?.length >= 3
      ? polygone(forme.points)
      : '';
}

function polygone(points) {
  return `polygon(${points.map(([x, y]) => `${x}% ${y}%`).join(', ')})`;
}

/* --- barre de commande ----------------------------------------------------- */

function majSommaire() {
  const photo = session?.images.find((image) => image.id === selection);
  $('#sommaire').classList.toggle('cache', !photo);
  if (!photo) return;

  if (estAffichable(photo.mime)) $('#sommaire-vignette').src = `/media/${photo.id}`;

  const matiere = cat.matieres.find((m) => m.cle === brouillon.matiere);
  const [largeur, hauteur] = dimensionsCourantes();
  const paysage = brouillon.orientation === 'paysage' && largeur !== hauteur;
  const forme = brouillon.forme === FORME_LIBRE
    ? { nom: 'Forme libre', geometrie: 'personnalise' }
    : cat.formes.find((f) => f.cle === brouillon.forme);

  const morceaux = [
    matiere?.nom,
    largeur && hauteur ? `${paysage ? hauteur : largeur} × ${paysage ? largeur : hauteur} cm` : null,
    brouillon.format === SUR_MESURE ? 'sur mesure' : null,
    forme && forme.geometrie !== 'rectangle' ? forme.nom : null,
  ].filter(Boolean);
  $('#sommaire-detail').textContent = morceaux.length ? morceaux.join(' • ') : 'À personnaliser';

  const montant = prixCourant();
  $('#prix-article').textContent = montant === null ? '—' : prixLisible(montant, cat.devise);

  // Total du dépôt, dès qu'il y a plus d'une photo.
  const choisies = session.images.filter((image) => image.article);
  const total = choisies.reduce((somme, image) => somme + image.article.prix, 0);
  $('#bloc-total').classList.toggle('cache', session.images.length < 2);
  $('#total-panier').textContent = choisies.length
    ? prixLisible(arrondi(total), cat.devise)
    : '—';
  $('#mention-total').textContent =
    `Total ${choisies.length}/${session.images.length} tirage${session.images.length > 1 ? 's' : ''}`;

  const restants = session.images.length - choisies.length;
  const pret = session.images.length > 0 && restants === 0;
  $('#btn-valider').disabled = !pret;
  $('#btn-valider').title = pret ? '' : `${restants} photo(s) sans tirage choisi`;
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
    masquerErreur();
    $('#bande-photos').replaceChildren(...session.images.map(vignetteBande));
    majSommaire();
  } catch (echec) {
    afficherErreur(`Choix impossible : ${echec.message}`);
  }
}

/* --- photos ---------------------------------------------------------------- */

function afficherApercu() {
  const total = session.images.length;
  const photo = session.images.find((image) => image.id === selection) || session.images.at(-1);
  if (!photo) return montrerEtape('etape-attente');
  selection = photo.id;

  $('#titre-apercu').textContent =
    total > 1 ? `Vos ${total} photos sont prêtes !` : 'Votre photo est prête !';

  const geante = $('#photo-geante');
  if (estAffichable(photo.mime)) {
    geante.src = `/media/${photo.id}`;
    geante.alt = photo.name;
    geante.classList.remove('cache');
  } else {
    geante.classList.add('cache');
  }

  $('#legende-photo').textContent = [
    photo.name, poids(photo.size),
    photo.width ? `${photo.width} × ${photo.height} px` : null,
  ].filter(Boolean).join(' · ');

  brouillon = photo.article
    ? {
        matiere: photo.article.matiere,
        format: photo.article.format,
        forme: photo.article.forme,
        orientation: photo.article.orientation || 'portrait',
        mesures: photo.article.mesures || null,
        points: photo.article.points || null,
      }
    : { ...vide(), orientation: orientationNaturelle(photo) };
  // `formeNeutre` lit `brouillon` : on ne l'appelle qu'une fois celui-ci posé.
  if (!photo.article) brouillon.forme = formeNeutre();

  if (brouillon.mesures) {
    $('#mesure-largeur').value = brouillon.mesures[0];
    $('#mesure-hauteur').value = brouillon.mesures[1];
  }

  // Une autre photo peut avoir un autre support : les listes se refont.
  construireFormats();
  construireFormes();
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
  ].filter(Boolean).join(' ');

  return element('li', {}, element('button', {
    class: classes,
    type: 'button',
    'aria-label': `${image.article ? 'Modifier' : 'Choisir'} le tirage de ${image.name}`,
    onclick: () => { selection = image.id; afficherApercu(); },
  }, contenu));
}

/* --- forme libre, dessinée par le client ------------------------------------ */

const MODELES = {
  coeur: [[50, 96], [12, 56], [8, 34], [22, 18], [38, 20], [50, 34],
    [62, 20], [78, 18], [92, 34], [88, 56]],
  etoile: (() => {
    const points = [];
    for (let i = 0; i < 10; i += 1) {
      const rayon = i % 2 === 0 ? 48 : 20;
      const angle = (Math.PI / 5) * i - Math.PI / 2;
      points.push([
        Number((50 + rayon * Math.cos(angle)).toFixed(1)),
        Number((50 + rayon * Math.sin(angle)).toFixed(1)),
      ]);
    }
    return points;
  })(),
};

let contour = [];
let poigneeTiree = null;

function ouvrirEditeurForme() {
  contour = (brouillon.points || MODELES.coeur).map((p) => [...p]);
  const photo = session.images.find((image) => image.id === selection);
  if (photo && estAffichable(photo.mime)) {
    $('#forme-photo').setAttributeNS('http://www.w3.org/1999/xlink', 'href', `/media/${photo.id}`);
    $('#forme-photo').setAttribute('href', `/media/${photo.id}`);
  }
  $('#forme-erreur').classList.add('cache');
  redessinerForme();
  $('#voile-forme').classList.remove('cache');
}

function redessinerForme() {
  $('#forme-contour').setAttribute('points', contour.map((p) => p.join(',')).join(' '));
  $('#forme-points').replaceChildren(
    ...contour.map((p, i) => {
      const cercle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      cercle.setAttribute('cx', p[0]);
      cercle.setAttribute('cy', p[1]);
      cercle.setAttribute('r', 2.6);
      cercle.setAttribute('class', 'poignee');
      cercle.addEventListener('pointerdown', (e) => {
        e.stopPropagation();
        poigneeTiree = { indice: i, bouge: false };
        $('#forme-svg').setPointerCapture(e.pointerId);
      });
      return cercle;
    }),
  );
}

function positionForme(evenement) {
  const cadre = $('#forme-svg').getBoundingClientRect();
  return [
    Math.max(0, Math.min(100, ((evenement.clientX - cadre.left) / cadre.width) * 100)),
    Math.max(0, Math.min(100, ((evenement.clientY - cadre.top) / cadre.height) * 100)),
  ].map((v) => Number(v.toFixed(1)));
}

$('#forme-svg').addEventListener('pointerdown', (e) => {
  if (poigneeTiree) return;
  contour.push(positionForme(e));
  redessinerForme();
});
$('#forme-svg').addEventListener('pointermove', (e) => {
  if (!poigneeTiree) return;
  poigneeTiree.bouge = true;
  contour[poigneeTiree.indice] = positionForme(e);
  redessinerForme();
});
$('#forme-svg').addEventListener('pointerup', () => {
  if (poigneeTiree && !poigneeTiree.bouge) {
    contour.splice(poigneeTiree.indice, 1);
    redessinerForme();
  }
  poigneeTiree = null;
});

$('#forme-coeur').addEventListener('click', () => {
  contour = MODELES.coeur.map((p) => [...p]); redessinerForme();
});
$('#forme-etoile').addEventListener('click', () => {
  contour = MODELES.etoile.map((p) => [...p]); redessinerForme();
});
$('#forme-vider').addEventListener('click', () => { contour = []; redessinerForme(); });
$('#forme-fermer').addEventListener('click', () => $('#voile-forme').classList.add('cache'));

$('#forme-valider').addEventListener('click', () => {
  if (contour.length < 3) {
    $('#forme-erreur').textContent = 'Posez au moins trois points pour dessiner une forme.';
    $('#forme-erreur').classList.remove('cache');
    return;
  }
  brouillon.forme = FORME_LIBRE;
  brouillon.points = contour.map((p) => [...p]);
  $('#voile-forme').classList.add('cache');
  appliquerChoix();
});

/* --- actions --------------------------------------------------------------- */

$('#btn-aide').addEventListener('click', () => $('#voile-aide').classList.remove('cache'));
$('#aide-fermer').addEventListener('click', () => $('#voile-aide').classList.add('cache'));

$('#btn-ajouter').addEventListener('click', () => montrerEtape('etape-attente'));

$('#btn-annuler').addEventListener('click', async () => {
  if (!window.confirm('Annuler ce dépôt et supprimer les photos reçues ?')) return;
  try {
    await api(`/api/sessions/${session.token}`, { method: 'DELETE' });
  } catch (echec) { /* la session avait peut-être déjà disparu */ }
  window.location.reload();
});

$('#btn-valider').addEventListener('click', async () => {
  const bouton = $('#btn-valider');
  bouton.disabled = true;
  try {
    afficherCode(await api(`/api/sessions/${session.token}/valider`, { method: 'POST' }));
  } catch (echec) {
    afficherErreur(`Validation impossible : ${echec.message}`);
    bouton.disabled = false;
  }
});

$('#btn-recommencer').addEventListener('click', () => window.location.reload());

/* --- code de retrait -------------------------------------------------------- */

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
    ? element('img', { class: 'vignette__image', src: `/media/${image.id}`, alt: image.name, loading: 'lazy' })
    : element('div', { class: 'vignette__vide' }, extension(image.mime));

  return element('li', { class: 'vignette' }, [
    apercu,
    element('div', { class: 'vignette__corps' }, [
      element('span', { class: 'vignette__nom', title: image.name }, image.name),
      element('span', { class: 'vignette__meta' },
        image.article
          ? `${image.article.libelle} · ${prixLisible(image.article.prix, cat.devise)}`
          : poids(image.size)),
    ]),
  ]);
}

/* --- navigation ------------------------------------------------------------- */

const ETAPES = { 'etape-attente': 'photo', 'etape-apercu': 'perso', 'etape-code': 'validation' };
const ORDRE = ['photo', 'perso', 'validation'];

function montrerEtape(identifiant) {
  for (const nom of Object.keys(ETAPES)) {
    $(`#${nom}`).classList.toggle('cache', nom !== identifiant);
  }
  $('#sommaire').classList.toggle('cache', identifiant !== 'etape-apercu');
  if (identifiant === 'etape-apercu') majSommaire();

  const courante = ORDRE.indexOf(ETAPES[identifiant]);
  for (const etape of document.querySelectorAll('.parcours__etape')) {
    const rang = ORDRE.indexOf(etape.dataset.etape);
    etape.dataset.etat = rang < courante ? 'fait' : rang === courante ? 'courant' : 'a-venir';
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* --- messages --------------------------------------------------------------- */

function afficherErreur(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
}

function masquerErreur() {
  erreur.classList.add('cache');
}
