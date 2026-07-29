/* Page d'administration : marque, catalogue, tarifs, encaissement. */

import { $, api, element, marquerPageActive } from './commun.js';

let etat = null;
let geometries = {};

marquerPageActive();
demarrer();

async function demarrer() {
  try {
    const recu = await api('/api/reglages');
    geometries = recu.geometries || {};
    remplir(recu);
  } catch (echec) {
    afficherErreur(`Impossible de lire les réglages : ${echec.message}`);
  }
}

function remplir(recu) {
  etat = recu;
  $('#nom-boutique').value = recu.boutique.nom || '';
  majCouleur('primaire', recu.theme.primaire);
  majCouleur('accent', recu.theme.accent);
  majLogo(recu.boutique.logo);

  $('#formes-actives').checked = Boolean(recu.catalogue.formes_actives);
  $('#mode-paiement').value = recu.paiement.mode || 'comptoir';
  $('#lien-paiement').value = recu.paiement.lien || '';
  $('#libelle-paiement').value = recu.paiement.libelle || '';
  majBlocLien();

  dessinerMatieres();
  dessinerFormats();
  dessinerFormes();
}

/* --- marque ---------------------------------------------------------------- */

function majCouleur(nom, valeur) {
  $(`#couleur-${nom}`).value = valeur;
  $(`#couleur-${nom}-texte`).value = valeur;
}

for (const nom of ['primaire', 'accent']) {
  $(`#couleur-${nom}`).addEventListener('input', (e) => {
    $(`#couleur-${nom}-texte`).value = e.target.value.toUpperCase();
  });
  $(`#couleur-${nom}-texte`).addEventListener('change', (e) => {
    const valeur = e.target.value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(valeur)) $(`#couleur-${nom}`).value = valeur;
    else e.target.value = $(`#couleur-${nom}`).value;
  });
}

function majLogo(nom) {
  const present = Boolean(nom);
  $('#apercu-logo').classList.toggle('cache', !present);
  $('#logo-vide').classList.toggle('cache', present);
  $('#btn-logo-suppr').classList.toggle('cache', !present);
  if (present) $('#apercu-logo').src = `/logo-boutique?t=${Date.now()}`;
  const entete = $('#logo-boutique');
  entete.classList.toggle('cache', !present);
  if (present) entete.src = `/logo-boutique?t=${Date.now()}`;
  else entete.removeAttribute('src');
}

$('#btn-logo').addEventListener('click', () => $('#champ-logo').click());

$('#champ-logo').addEventListener('change', async () => {
  const fichier = $('#champ-logo').files[0];
  $('#champ-logo').value = '';
  if (!fichier) return;
  try {
    const recu = await api('/api/reglages/logo', {
      method: 'POST',
      headers: { 'Content-Type': fichier.type || 'application/octet-stream' },
      body: fichier,
    });
    majLogo(recu.logo);
    signaler('Logo mis à jour');
  } catch (echec) {
    afficherErreur(echec.message);
  }
});

$('#btn-logo-suppr').addEventListener('click', async () => {
  try {
    await api('/api/reglages/logo', { method: 'DELETE' });
    majLogo(null);
    signaler('Logo retiré');
  } catch (echec) {
    afficherErreur(echec.message);
  }
});

/* --- tableaux du catalogue -------------------------------------------------- */

function ligne(cellules, surSuppression) {
  return element('div', { class: 'tableau__ligne' }, [
    ...cellules,
    element(
      'button',
      { class: 'tableau__suppr', type: 'button', title: 'Supprimer', onclick: surSuppression },
      '✕',
    ),
  ]);
}

function cellule(libelle, champ) {
  return element('label', { class: 'tableau__cellule' }, [
    element('span', { class: 'tableau__libelle' }, libelle),
    champ,
  ]);
}

function saisie(valeur, options = {}) {
  return element('input', { value: valeur, ...options });
}

function dessinerMatieres() {
  const lignes = etat.catalogue.matieres.map((m, i) =>
    ligne(
      [
        cellule('Nom', saisie(m.nom, {
          type: 'text', maxlength: 60,
          oninput: (e) => { m.nom = e.target.value; },
        })),
        cellule('Coefficient', saisie(m.coefficient, {
          type: 'number', step: '0.05', min: '0.01',
          oninput: (e) => { m.coefficient = Number(e.target.value); },
        })),
        element('label', { class: 'tableau__cellule tableau__cellule--case' }, [
          element('input', {
            type: 'checkbox', checked: m.decoupe ? '' : null,
            onchange: (e) => { m.decoupe = e.target.checked; },
          }),
          element('span', {}, 'Se découpe'),
        ]),
      ],
      () => {
        if (etat.catalogue.matieres.length <= 1) {
          return afficherErreur('Il faut garder au moins une matière.');
        }
        etat.catalogue.matieres.splice(i, 1);
        dessinerMatieres();
      },
    ),
  );
  $('#tableau-matieres').replaceChildren(...lignes);
}

function dessinerFormats() {
  const lignes = etat.catalogue.formats.map((f, i) =>
    ligne(
      [
        cellule('Nom', saisie(f.nom, {
          type: 'text', maxlength: 30,
          oninput: (e) => { f.nom = e.target.value; },
        })),
        cellule('Largeur (cm)', saisie(f.largeur, {
          type: 'number', min: '1', step: '1',
          oninput: (e) => { f.largeur = Number(e.target.value); },
        })),
        cellule('Hauteur (cm)', saisie(f.hauteur, {
          type: 'number', min: '1', step: '1',
          oninput: (e) => { f.hauteur = Number(e.target.value); },
        })),
        cellule('Prix de base (€)', saisie(f.prix, {
          type: 'number', min: '0', step: '0.5',
          oninput: (e) => { f.prix = Number(e.target.value); },
        })),
      ],
      () => {
        if (etat.catalogue.formats.length <= 1) {
          return afficherErreur('Il faut garder au moins un format.');
        }
        etat.catalogue.formats.splice(i, 1);
        dessinerFormats();
      },
    ),
  );
  $('#tableau-formats').replaceChildren(...lignes);
}

function dessinerFormes() {
  const lignes = etat.catalogue.formes.map((f, i) => {
    const rectangulaire = f.geometrie === 'rectangle';
    return ligne(
      [
        cellule('Nom', saisie(f.nom, {
          type: 'text', maxlength: 40,
          oninput: (e) => { f.nom = e.target.value; },
        })),
        cellule('Découpe', element(
          'select',
          { onchange: (e) => { f.geometrie = e.target.value; dessinerFormes(); } },
          Object.entries(geometries).map(([cle, nom]) =>
            element('option', { value: cle, selected: cle === f.geometrie ? '' : null }, nom),
          ),
        )),
        cellule('Supplément (€)', saisie(f.supplement, {
          type: 'number', min: '0', step: '0.5',
          oninput: (e) => { f.supplement = Number(e.target.value); },
        })),
      ],
      () => {
        if (rectangulaire) {
          return afficherErreur(
            'Le tirage rectangulaire ne peut pas être supprimé : c\'est le tirage sans découpe.',
          );
        }
        etat.catalogue.formes.splice(i, 1);
        dessinerFormes();
      },
    );
  });
  $('#tableau-formes').replaceChildren(...lignes);
}

$('#btn-ajout-matiere').addEventListener('click', () => {
  etat.catalogue.matieres.push({ cle: '', nom: '', coefficient: 1, decoupe: true });
  dessinerMatieres();
});

$('#btn-ajout-format').addEventListener('click', () => {
  etat.catalogue.formats.push({ cle: '', nom: '', largeur: 30, hauteur: 40, prix: 0 });
  dessinerFormats();
});

$('#btn-ajout-forme').addEventListener('click', () => {
  etat.catalogue.formes.push({ cle: '', nom: '', geometrie: 'cercle', supplement: 0 });
  dessinerFormes();
});

/* --- encaissement ----------------------------------------------------------- */

$('#mode-paiement').addEventListener('change', majBlocLien);

function majBlocLien() {
  $('#bloc-lien').classList.toggle('cache', $('#mode-paiement').value !== 'lien');
}

/* --- enregistrement --------------------------------------------------------- */

$('#btn-enregistrer').addEventListener('click', async () => {
  masquerErreur();
  const bouton = $('#btn-enregistrer');
  bouton.disabled = true;

  const charge = {
    boutique: { nom: $('#nom-boutique').value },
    theme: {
      primaire: $('#couleur-primaire').value,
      accent: $('#couleur-accent').value,
    },
    catalogue: {
      formes_actives: $('#formes-actives').checked,
      matieres: etat.catalogue.matieres,
      formats: etat.catalogue.formats,
      formes: etat.catalogue.formes,
    },
    paiement: {
      mode: $('#mode-paiement').value,
      lien: $('#lien-paiement').value,
      libelle: $('#libelle-paiement').value,
    },
  };

  try {
    remplir({ ...(await api('/api/reglages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charge),
    })), geometries });
    signaler('Réglages enregistrés');
    // Les couleurs sont servies par une feuille générée : on la recharge.
    setTimeout(() => window.location.reload(), 600);
  } catch (echec) {
    afficherErreur(echec.message);
  } finally {
    bouton.disabled = false;
  }
});

$('#btn-defaut').addEventListener('click', async () => {
  if (!window.confirm('Revenir au catalogue et aux couleurs d\'origine ?')) return;
  try {
    await api('/api/reglages', { method: 'DELETE' });
  } catch (echec) {
    afficherErreur(echec.message);
    return;
  }
  window.location.reload();
});

/* --- messages --------------------------------------------------------------- */

function signaler(texte) {
  const etiquette = $('#etat-enregistrement');
  etiquette.textContent = texte;
  setTimeout(() => { etiquette.textContent = ''; }, 3000);
}

function afficherErreur(texte) {
  const boite = $('#message-erreur');
  boite.textContent = texte;
  boite.classList.remove('cache');
  boite.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function masquerErreur() {
  $('#message-erreur').classList.add('cache');
}
