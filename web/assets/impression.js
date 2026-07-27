/* Page d'impression : une image en grand, prête à partir chez l'imprimante. */

import { $, api, marquerPageActive, poids } from './commun.js';

marquerPageActive();

const parametres = new URLSearchParams(window.location.search);
const identifiant = parametres.get('image');

const image = $('#image');
const erreur = $('#message-erreur');

if (!identifiant) {
  echouer("Aucune image demandée. Revenez au dépôt pour en choisir une.");
} else {
  image.src = `/media/${identifiant}`;
  $('#btn-telecharger').href = `/media/${identifiant}?dl=1`;
  chargerDetails(identifiant);
}

image.addEventListener('error', () => {
  echouer("Cette image n'est plus disponible : le dépôt a peut-être expiré ou été supprimé.");
});

image.addEventListener('load', () => {
  if (parametres.get('auto') === '1') window.print();
});

$('#btn-imprimer').addEventListener('click', () => window.print());

/* Le détail (nom, dimensions) n'est pas indispensable : on l'ajoute si on le trouve. */
async function chargerDetails(cible) {
  let depots = [];
  try {
    depots = await api('/api/depots');
  } catch (echec) {
    return;
  }

  for (const depot of depots) {
    const trouvee = depot.images.find((element) => element.id === cible);
    if (!trouvee) continue;

    document.title = `${trouvee.name} — Symp's Kiosk`;
    $('#titre-image').textContent = trouvee.name;
    $('#details-image').textContent =
      [
        `Dépôt ${depot.code}`,
        poids(trouvee.size),
        trouvee.width ? `${trouvee.width} × ${trouvee.height} px` : null,
      ]
        .filter(Boolean)
        .join(' · ');
    image.alt = trouvee.name;
    $('#btn-retour').href = `/recuperer?code=${depot.code}`;
    return;
  }
}

function echouer(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
  $('#btn-imprimer').disabled = true;
  image.classList.add('cache');
}
