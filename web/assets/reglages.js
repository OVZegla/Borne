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

  const mode = recu.catalogue.tarification || 'coefficient';
  $(`#mode-${mode}`).checked = true;
  majTarification();

  $('#formes-actives').checked = Boolean(recu.catalogue.formes_actives);
  $('#mode-paiement').value = recu.paiement.mode || 'comptoir';
  $('#lien-paiement').value = recu.paiement.lien || '';
  $('#libelle-paiement').value = recu.paiement.libelle || '';
  majBlocLien();

  dessinerMatieres();
  dessinerFormats();
  dessinerFormes();
}

/* --- mode de tarification --------------------------------------------------- */

function modeActuel() {
  return $('#mode-surface').checked ? 'surface' : 'coefficient';
}

for (const id of ['#mode-coefficient', '#mode-surface']) {
  $(id).addEventListener('change', () => { majTarification(); dessinerMatieres(); dessinerFormats(); });
}

/** Explique le mode retenu avec un exemple chiffré, pris dans le catalogue. */
function majTarification() {
  const surface = modeActuel() === 'surface';

  $('#aide-matieres').innerHTML = surface
    ? 'Donnez le <strong>prix au m²</strong> de chaque matière. Le prix d\'un tirage '
      + 'vaut alors <strong>surface × prix au m² + supplément de coupe</strong>.'
    : 'Le <strong>coefficient</strong> multiplie le prix du format. Un coefficient de '
      + '<strong>1</strong> vend au prix du format ; <strong>1,5</strong> le vend '
      + 'moitié plus cher ; <strong>2</strong> le double. Le prix d\'un tirage vaut '
      + '<strong>prix du format × coefficient + supplément de coupe</strong>.';

  $('#aide-formats').innerHTML = surface
    ? 'Le prix se calcule à partir des dimensions : la colonne « prix » est ignorée '
      + 'dans ce mode. Saisissez les dimensions en portrait, le client choisira '
      + 'lui-même portrait ou paysage.'
    : 'Saisissez les dimensions en portrait (largeur inférieure à la hauteur) : le '
      + 'client choisira lui-même portrait ou paysage sur la borne.';

  majExemple();
}

function majExemple() {
  if (!etat) return;
  const surface = modeActuel() === 'surface';
  const matiere = etat.catalogue.matieres[0];
  const format = etat.catalogue.formats[0];
  if (!matiere || !format) return ($('#exemple-tarif').textContent = '');

  const aire = (format.largeur / 100) * (format.hauteur / 100);
  const base = surface ? aire * (matiere.prix_m2 || 0) : (format.prix || 0) * (matiere.coefficient || 0);
  const detail = surface
    ? `${format.largeur} × ${format.hauteur} cm = ${aire.toFixed(2)} m², × `
      + `${euros(matiere.prix_m2)}/m²`
    : `${euros(format.prix)} × ${matiere.coefficient}`;

  $('#exemple-tarif').replaceChildren(
    element('span', { class: 'exemple__etiquette' }, 'Exemple'),
    element('span', {}, [
      element('strong', {}, `${matiere.nom} en ${format.nom} cm`),
      ` : ${detail} = `,
      element('strong', { class: 'exemple__prix' }, euros(base)),
    ]),
  );
}

function euros(valeur) {
  return `${Number(valeur || 0).toFixed(2).replace('.', ',')} €`;
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
    ...cellules.filter(Boolean),
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
        modeActuel() === 'surface'
          ? cellule('Prix au m² (€)', saisie(m.prix_m2, {
              type: 'number', step: '5', min: '0',
              oninput: (e) => { m.prix_m2 = Number(e.target.value); majExemple(); },
            }))
          : cellule('Coefficient', saisie(m.coefficient, {
              type: 'number', step: '0.05', min: '0.01',
              oninput: (e) => { m.coefficient = Number(e.target.value); majExemple(); },
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
          oninput: (e) => { f.largeur = Number(e.target.value); majExemple(); },
        })),
        cellule('Hauteur (cm)', saisie(f.hauteur, {
          type: 'number', min: '1', step: '1',
          oninput: (e) => { f.hauteur = Number(e.target.value); majExemple(); },
        })),
        modeActuel() === 'surface'
          ? null
          : cellule('Prix de base (€)', saisie(f.prix, {
              type: 'number', min: '0', step: '0.5',
              oninput: (e) => { f.prix = Number(e.target.value); majExemple(); },
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
          { onchange: (e) => {
              f.geometrie = e.target.value;
              if (f.geometrie === 'personnalise' && !f.points?.length) {
                f.points = PRESETS.losange.map((p) => [...p]);
              }
              dessinerFormes();
            } },
          Object.entries(geometries).map(([cle, nom]) =>
            element('option', { value: cle, selected: cle === f.geometrie ? '' : null }, nom),
          ),
        )),
        cellule('Supplément (€)', saisie(f.supplement, {
          type: 'number', min: '0', step: '0.5',
          oninput: (e) => { f.supplement = Number(e.target.value); },
        })),
        f.geometrie === 'personnalise'
          ? element('div', { class: 'tableau__cellule tableau__cellule--case' }, [
              element('button', {
                class: 'bouton bouton--secondaire', type: 'button',
                onclick: () => ouvrirEditeur(f),
              }, f.points?.length ? 'Modifier le dessin' : 'Dessiner…'),
            ])
          : null,
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
      tarification: modeActuel(),
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

/* --- éditeur de coupe (côté boutique uniquement) ---------------------------- */

const PRESETS = {
  carre: [[10, 10], [90, 10], [90, 90], [10, 90]],
  losange: [[50, 2], [98, 50], [50, 98], [2, 50]],
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

let formeEnCours = null;
let points = [];
let pointTire = null;

function ouvrirEditeur(forme) {
  formeEnCours = forme;
  points = (forme.points || []).map((p) => [...p]);
  $('#editeur-titre').textContent = `Dessiner « ${forme.nom || 'la coupe'} »`;
  $('#editeur-erreur').classList.add('cache');
  redessiner();
  $('#voile-editeur').classList.remove('cache');
}

function fermerEditeur() {
  $('#voile-editeur').classList.add('cache');
  formeEnCours = null;
  pointTire = null;
}

function coordonnees(evenement) {
  const svg = $('#editeur-svg');
  const cadre = svg.getBoundingClientRect();
  return [
    Math.max(0, Math.min(100, ((evenement.clientX - cadre.left) / cadre.width) * 100)),
    Math.max(0, Math.min(100, ((evenement.clientY - cadre.top) / cadre.height) * 100)),
  ].map((v) => Number(v.toFixed(1)));
}

function redessiner() {
  $('#editeur-contour').setAttribute('points', points.map((p) => p.join(',')).join(' '));
  $('#editeur-points').replaceChildren(
    ...points.map((p, i) => {
      const poignee = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      poignee.setAttribute('cx', p[0]);
      poignee.setAttribute('cy', p[1]);
      poignee.setAttribute('r', 2.4);
      poignee.setAttribute('class', 'poignee');
      poignee.addEventListener('pointerdown', (e) => {
        e.stopPropagation();
        pointTire = { indice: i, bouge: false };
        $('#editeur-svg').setPointerCapture(e.pointerId);
      });
      return poignee;
    }),
  );
}

$('#editeur-svg').addEventListener('pointerdown', (evenement) => {
  if (pointTire) return;
  points.push(coordonnees(evenement));
  redessiner();
});

$('#editeur-svg').addEventListener('pointermove', (evenement) => {
  if (!pointTire) return;
  pointTire.bouge = true;
  points[pointTire.indice] = coordonnees(evenement);
  redessiner();
});

$('#editeur-svg').addEventListener('pointerup', () => {
  // Un clic sans déplacement retire le point : c'est la façon la plus directe
  // de corriger un contour sans multiplier les boutons.
  if (pointTire && !pointTire.bouge) {
    points.splice(pointTire.indice, 1);
    redessiner();
  }
  pointTire = null;
});

for (const [nom, preset] of Object.entries(PRESETS)) {
  $(`#editeur-${nom}`).addEventListener('click', () => {
    points = preset.map((p) => [...p]);
    redessiner();
  });
}

$('#editeur-vider').addEventListener('click', () => { points = []; redessiner(); });
$('#editeur-fermer').addEventListener('click', fermerEditeur);

$('#editeur-valider').addEventListener('click', () => {
  if (points.length < 3) {
    $('#editeur-erreur').textContent = 'Il faut au moins trois points pour dessiner une forme.';
    $('#editeur-erreur').classList.remove('cache');
    return;
  }
  formeEnCours.points = points.map((p) => [...p]);
  fermerEditeur();
  dessinerFormes();
  signaler('Forme enregistrée — pensez à cliquer sur Enregistrer');
});
