/* Page de dépôt : envoi des fichiers puis affichage du code de retrait. */

import {
  $, api, config, element, estAffichable, extension, marquerPageActive, poids,
} from './commun.js';

const zone = $('#zone-depot');
const champ = $('#champ-fichier');
const file = $('#file-envoi');
const erreur = $('#message-erreur');

let reglages = null;
let depot = null; // { code, images: [] }
let envoisEnCours = 0;

marquerPageActive();

config()
  .then((valeurs) => {
    reglages = valeurs;
    $('#retention').textContent = valeurs.retention_heures;
    $('#aide-depot').textContent =
      `ou cliquez pour choisir un fichier — ${valeurs.taille_max_mo} Mo maximum par image`;
  })
  .catch(() => afficherErreur("Impossible de contacter la borne. Le serveur tourne-t-il toujours ?"));

/* --- interactions ---------------------------------------------------------- */

zone.addEventListener('click', () => champ.click());
zone.addEventListener('keydown', (evenement) => {
  if (evenement.key === 'Enter' || evenement.key === ' ') {
    evenement.preventDefault();
    champ.click();
  }
});

$('#btn-parcourir').addEventListener('click', () => {
  champ.removeAttribute('capture');
  champ.click();
});

$('#btn-photo').addEventListener('click', () => {
  champ.setAttribute('capture', 'environment');
  champ.click();
});

champ.addEventListener('change', () => {
  traiter([...champ.files]);
  champ.value = '';
});

for (const nom of ['dragenter', 'dragover']) {
  zone.addEventListener(nom, (evenement) => {
    evenement.preventDefault();
    zone.classList.add('survol');
  });
}

for (const nom of ['dragleave', 'drop']) {
  zone.addEventListener(nom, (evenement) => {
    evenement.preventDefault();
    if (nom === 'dragleave' && zone.contains(evenement.relatedTarget)) return;
    zone.classList.remove('survol');
  });
}

zone.addEventListener('drop', (evenement) => {
  traiter([...(evenement.dataTransfer?.files || [])]);
});

// Le collage est pratique sur une borne pilotée au clavier.
document.addEventListener('paste', (evenement) => {
  const fichiers = [...(evenement.clipboardData?.files || [])];
  if (fichiers.length) traiter(fichiers);
});

$('#btn-terminer').addEventListener('click', afficherCode);
$('#btn-nouveau').addEventListener('click', () => window.location.reload());

/* --- envoi ----------------------------------------------------------------- */

async function traiter(fichiers) {
  if (!fichiers.length) return;
  masquerErreur();

  // Inutile d'envoyer un fichier que la borne refusera : on le dit tout de suite.
  const limite = reglages ? reglages.taille_max_mo * 1024 * 1024 : Infinity;
  const acceptes = fichiers.filter((fichier) => fichier.size <= limite);
  const refuses = fichiers.filter((fichier) => fichier.size > limite);

  if (refuses.length) {
    const noms = refuses.map((fichier) => fichier.name).join(', ');
    afficherErreur(`${noms} — trop volumineux (maximum ${reglages.taille_max_mo} Mo par fichier).`);
  }
  if (!acceptes.length) return;

  if (reglages) {
    const total = (depot?.images.length || 0) + envoisEnCours + acceptes.length;
    if (total > reglages.fichiers_max) {
      afficherErreur(`Ce dépôt est limité à ${reglages.fichiers_max} fichiers.`);
      return;
    }
  }

  try {
    if (!depot) {
      const cree = await api('/api/depots', { method: 'POST' });
      depot = { code: cree.code, images: [] };
    }
  } catch (echec) {
    afficherErreur(`Impossible d'ouvrir un dépôt : ${echec.message}`);
    return;
  }

  for (const fichier of acceptes) envoyer(fichier);
}

function envoyer(fichier) {
  const vue = ligneFichier(fichier);
  file.append(vue.noeud);
  envoisEnCours += 1;
  majBoutonTerminer();

  const requete = new XMLHttpRequest();
  requete.open('POST', `/api/depots/${depot.code}/images`);
  requete.setRequestHeader('Content-Type', fichier.type || 'application/octet-stream');
  requete.setRequestHeader('X-Nom-Fichier', encodeURIComponent(fichier.name || 'image'));

  requete.upload.addEventListener('progress', (evenement) => {
    if (!evenement.lengthComputable) return;
    vue.progresser(Math.round((evenement.loaded / evenement.total) * 100));
  });

  requete.addEventListener('load', () => {
    envoisEnCours -= 1;
    let reponse = null;
    try {
      reponse = JSON.parse(requete.responseText);
    } catch (echec) {
      reponse = null;
    }

    if (requete.status >= 200 && requete.status < 300 && reponse) {
      depot.images.push(reponse);
      vue.reussir();
    } else {
      vue.echouer((reponse && reponse.erreur) || `Refusé (${requete.status})`);
    }
    majBoutonTerminer();
  });

  requete.addEventListener('error', () => {
    envoisEnCours -= 1;
    vue.echouer('Échec réseau');
    majBoutonTerminer();
  });

  requete.send(fichier);
}

function ligneFichier(fichier) {
  const barre = element('span', { class: 'jauge__barre' });
  const etat = element('span', { class: 'ligne__etat' }, 'Envoi…');
  const vignette = element('img', {
    class: 'ligne__vignette',
    alt: '',
    src: estAffichable(fichier.type) ? URL.createObjectURL(fichier) : '/assets/logo.svg',
  });

  const noeud = element('li', { class: 'ligne' }, [
    vignette,
    element('span', {}, [
      element('span', { class: 'ligne__nom' }, fichier.name || 'image'),
      element('span', { class: 'ligne__detail' }, poids(fichier.size)),
      element('span', { class: 'jauge' }, [barre]),
    ]),
    etat,
  ]);

  return {
    noeud,
    progresser(pourcentage) {
      barre.style.width = `${pourcentage}%`;
      etat.textContent = `${pourcentage} %`;
    },
    reussir() {
      barre.style.width = '100%';
      etat.textContent = 'Ajouté';
      etat.className = 'ligne__etat ligne__etat--ok';
    },
    echouer(message) {
      barre.style.width = '0';
      etat.textContent = message;
      etat.className = 'ligne__etat ligne__etat--erreur';
    },
  };
}

function majBoutonTerminer() {
  const bouton = $('#btn-terminer');
  const pret = envoisEnCours === 0 && depot && depot.images.length > 0;
  bouton.classList.toggle('cache', !pret);
  bouton.disabled = !pret;
}

/* --- écran du code --------------------------------------------------------- */

async function afficherCode() {
  const reglagesSurs = reglages || (await config().catch(() => null));
  const base = reglagesSurs?.url_reseau || window.location.origin;
  const lien = `${base}/r?c=${depot.code}`;

  $('#affichage-code').textContent = depot.code;
  $('#image-qr').src = `/qr.svg?d=${encodeURIComponent(lien)}`;
  $('#url-reseau').textContent = `${base}/recuperer`;
  $('#lien-recuperer').href = `/recuperer?code=${depot.code}`;

  const nombre = depot.images.length;
  $('#resume-depot').textContent =
    `${nombre} ${nombre > 1 ? 'fichiers déposés' : 'fichier déposé'} · ` +
    `disponible ${reglagesSurs ? reglagesSurs.retention_heures : 24} h`;

  const galerie = $('#galerie-depot');
  galerie.replaceChildren(...depot.images.map(carteImage));

  $('#etape-depot').classList.add('cache');
  $('#etape-code').classList.remove('cache');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function carteImage(image) {
  const apercu = estAffichable(image.mime)
    ? element('img', { class: 'vignette__image', src: `/media/${image.id}`, alt: image.name, loading: 'lazy' })
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

/* --- messages -------------------------------------------------------------- */

function afficherErreur(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
}

function masquerErreur() {
  erreur.classList.add('cache');
}
