/* Page ouverte sur le téléphone après avoir scanné le QR code de la borne. */

import { $, api, config, element, estAffichable, poids } from './commun.js';

const champ = $('#champ-fichier');
const file = $('#file-envoi');
const erreur = $('#message-erreur');
const succes = $('#message-succes');

const jeton = new URLSearchParams(window.location.search).get('s');

let reglages = null;
let envoisEnCours = 0;
let envoyees = 0;

demarrer();

async function demarrer() {
  if (!jeton) {
    return bloquer('Lien incomplet. Scannez à nouveau le QR code affiché sur la borne.');
  }

  try {
    reglages = await config();
    $('#chapeau').textContent =
      `Elles s'afficheront aussitôt sur l'écran de la borne. ` +
      `${reglages.taille_max_mo} Mo maximum par photo.`;
  } catch (echec) {
    return bloquer("La borne n'est plus joignable. Vérifiez que vous êtes bien sur son réseau.");
  }

  try {
    const session = await api(`/api/sessions/${jeton}`);
    if (session.validee) {
      bloquer('Ce dépôt est déjà validé. Repartez de la borne pour en ouvrir un nouveau.');
    }
  } catch (echec) {
    bloquer('Cette session a expiré. Scannez à nouveau le QR code affiché sur la borne.');
  }
}

/* --- sélection des fichiers ------------------------------------------------ */

$('#btn-photo').addEventListener('click', () => {
  champ.setAttribute('capture', 'environment');
  champ.click();
});

$('#btn-galerie').addEventListener('click', () => {
  champ.removeAttribute('capture');
  champ.click();
});

$('#btn-encore').addEventListener('click', () => {
  $('#etape-fin').classList.add('cache');
  $('#etape-envoi').classList.remove('cache');
});

champ.addEventListener('change', () => {
  traiter([...champ.files]);
  champ.value = '';
});

function traiter(fichiers) {
  if (!fichiers.length) return;
  masquerMessages();

  const limite = reglages ? reglages.taille_max_mo * 1024 * 1024 : Infinity;
  const acceptes = fichiers.filter((fichier) => fichier.size <= limite);
  const refuses = fichiers.filter((fichier) => fichier.size > limite);

  if (refuses.length) {
    const noms = refuses.map((fichier) => fichier.name).join(', ');
    afficherErreur(`${noms} — trop volumineux (maximum ${reglages.taille_max_mo} Mo par photo).`);
  }
  if (!acceptes.length) return;

  if (reglages && envoyees + envoisEnCours + acceptes.length > reglages.fichiers_max) {
    return afficherErreur(`Ce dépôt est limité à ${reglages.fichiers_max} photos.`);
  }

  for (const fichier of acceptes) envoyer(fichier);
}

/* --- envoi ----------------------------------------------------------------- */

function envoyer(fichier) {
  const vue = ligneFichier(fichier);
  file.prepend(vue.noeud);
  envoisEnCours += 1;

  const requete = new XMLHttpRequest();
  requete.open('POST', `/api/sessions/${jeton}/images`);
  requete.setRequestHeader('Content-Type', fichier.type || 'application/octet-stream');
  requete.setRequestHeader('X-Nom-Fichier', encodeURIComponent(fichier.name || 'photo'));

  requete.upload.addEventListener('progress', (evenement) => {
    if (evenement.lengthComputable) {
      vue.progresser(Math.round((evenement.loaded / evenement.total) * 100));
    }
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
      envoyees += 1;
      vue.reussir();
      terminerSiPret();
    } else {
      vue.echouer((reponse && reponse.erreur) || `Refusé (${requete.status})`);
    }
  });

  requete.addEventListener('error', () => {
    envoisEnCours -= 1;
    vue.echouer('Échec réseau');
  });

  requete.send(fichier);
}

function terminerSiPret() {
  if (envoisEnCours > 0 || !envoyees) return;
  $('#resume-fin').textContent =
    `${envoyees} ${envoyees > 1 ? 'photos envoyées' : 'photo envoyée'} à la borne.`;
  $('#etape-envoi').classList.add('cache');
  $('#etape-fin').classList.remove('cache');
  window.scrollTo({ top: 0, behavior: 'smooth' });
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
      element('span', { class: 'ligne__nom' }, fichier.name || 'photo'),
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
      etat.textContent = 'Envoyée';
      etat.className = 'ligne__etat ligne__etat--ok';
    },
    echouer(message) {
      barre.style.width = '0';
      etat.textContent = message;
      etat.className = 'ligne__etat ligne__etat--erreur';
    },
  };
}

/* --- messages -------------------------------------------------------------- */

function bloquer(texte) {
  afficherErreur(texte);
  $('#btn-photo').disabled = true;
  $('#btn-galerie').disabled = true;
}

function afficherErreur(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
}

function masquerMessages() {
  erreur.classList.add('cache');
  succes.classList.add('cache');
}
