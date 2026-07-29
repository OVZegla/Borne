/* Page d'administration : marque, catalogue, tarifs, encaissement. */

import { $, api, element, marquerPageActive } from './commun.js';
import { creerRoue } from './roue.js';

let etat = null;
let geometries = {};
const roues = {};

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
  $('#place-nom').textContent = recu.boutique.nom || 'Borne';
  installerCouleurs(recu.theme);
  majLogo(recu.boutique.logo);

  const mode = recu.catalogue.tarification || 'coefficient';
  $(`#mode-${mode}`).checked = true;
  majTarification();

  recu.catalogue.sur_mesure = recu.catalogue.sur_mesure || { actif: false, min_cm: 10, max_cm: 120 };
  recu.catalogue.forme_libre = recu.catalogue.forme_libre || { actif: false, supplement: 0 };

  const mesure = recu.catalogue.sur_mesure;
  $('#sur-mesure-actif').checked = Boolean(mesure.actif);
  $('#sur-mesure-min').value = mesure.min_cm ?? 10;
  $('#sur-mesure-max').value = mesure.max_cm ?? 120;

  const libre = recu.catalogue.forme_libre;
  $('#forme-libre-actif').checked = Boolean(libre.actif);
  $('#forme-libre-supplement').value = libre.supplement ?? 0;
  majOptions();

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
    ? `${format.largeur} × ${format.hauteur} cm = ${decimal(aire)} m², × `
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

function decimal(valeur, chiffres = 2) {
  return Number(valeur || 0).toFixed(chiffres).replace('.', ',');
}

/* --- couleurs : trois roues et un aperçu vivant ------------------------------ */

const TEINTES = ['primaire', 'accent', 'fond'];

// Quelques accords tout prêts, pour partir de quelque chose plutôt que du bleu.
const PALETTES = [
  { nom: 'Symp\'s', primaire: '#00287E', accent: '#3D6FE0', fond: '#F2F6FD' },
  { nom: 'Ardoise', primaire: '#8FA8FF', accent: '#5C7CFA', fond: '#12151C' },
  { nom: 'Terre', primaire: '#7A3E1D', accent: '#C4703A', fond: '#FBF5EF' },
  { nom: 'Forêt', primaire: '#14532D', accent: '#2F9E5E', fond: '#F1F8F3' },
  { nom: 'Prune', primaire: '#4A1D5E', accent: '#9B5DE5', fond: '#F8F3FC' },
];

function installerCouleurs(theme) {
  if (roues.primaire) {
    for (const nom of TEINTES) roues[nom].definir(theme[nom]);
    return majApercuTheme();
  }
  for (const nom of TEINTES) {
    roues[nom] = creerRoue($(`#roue-${nom}`), {
      valeur: theme[nom],
      onChange: majApercuTheme,
    });
  }
  $('#palettes').replaceChildren(
    ...PALETTES.map((palette) =>
      element(
        'button',
        {
          class: 'palette', type: 'button', title: palette.nom,
          style: `--a:${palette.primaire};--b:${palette.accent};--c:${palette.fond}`,
          onclick: () => {
            for (const nom of TEINTES) roues[nom].definir(palette[nom]);
            majApercuTheme();
          },
        },
        element('span', { class: 'palette__nom' }, palette.nom),
      ),
    ),
  );
  majApercuTheme();
}

function couleurs() {
  return Object.fromEntries(TEINTES.map((nom) => [nom, roues[nom].valeur()]));
}

/** Luminosité perçue, même formule que le serveur : elle décide clair ou sombre. */
function clarte(hexa) {
  const [r, v, b] = [1, 3, 5].map((i) => parseInt(hexa.slice(i, i + 2), 16));
  return (r * 299 + v * 587 + b * 114) / 255000;
}

function melanger(hexa, vers, part) {
  const canaux = [1, 3, 5].map((i) => parseInt(hexa.slice(i, i + 2), 16));
  return `#${canaux.map((c) => Math.round(c + (vers - c) * part).toString(16).padStart(2, '0')).join('')}`;
}

/** L'aperçu applique les mêmes règles que la feuille générée par le serveur. */
function majApercuTheme() {
  const { primaire, accent, fond } = couleurs();
  const sombre = clarte(fond) < 0.5;
  const scene = $('#apercu-theme');
  scene.style.setProperty('--a-fond', fond);
  scene.style.setProperty('--a-surface', sombre ? melanger(fond, 255, 0.1) : '#ffffff');
  scene.style.setProperty('--a-encre', sombre ? '#f4f7ff' : melanger(primaire, 0, 0.84));
  scene.style.setProperty('--a-gris', melanger(sombre ? fond : primaire, 255, sombre ? 0.62 : 0.55));
  scene.style.setProperty('--a-bordure', melanger(accent, sombre ? 0 : 255, sombre ? 0.6 : 0.82));
  scene.style.setProperty('--a-primaire', sombre ? melanger(primaire, 255, 0.3) : primaire);
  scene.style.setProperty('--a-accent', accent);
  scene.dataset.sombre = String(sombre);

  // Les deux aperçus de place reprennent le même thème, et la signature Symp's
  // y passe en blanc dès que le fond est sombre — comme sur la borne.
  for (const place of document.querySelectorAll('.place__scene')) {
    place.style.setProperty('--a-fond', sombre ? melanger(fond, 255, 0.06) : '#ffffff');
    place.style.setProperty('--a-encre', sombre ? '#f4f7ff' : melanger(primaire, 0, 0.84));
    place.style.setProperty('--a-gris', melanger(sombre ? fond : primaire, 255, sombre ? 0.62 : 0.55));
    place.style.setProperty('--a-bordure', melanger(accent, sombre ? 0 : 255, sombre ? 0.6 : 0.82));
    place.style.setProperty('--a-primaire', sombre ? melanger(primaire, 255, 0.3) : primaire);
    place.style.setProperty('--a-filtre', sombre ? 'brightness(0) invert(1)' : 'none');
    place.style.setProperty('--a-plaque', sombre ? '#ffffff' : 'transparent');
    place.style.setProperty('--a-marge', sombre ? '3px 5px' : '0');
  }
}

function majLogo(nom) {
  const present = Boolean(nom);
  const adresse = `/logo-boutique?t=${Date.now()}`;

  $('#logo-vide').classList.toggle('cache', present);
  $('#btn-logo-suppr').classList.toggle('cache', !present);

  // Toutes les places où le logo de la boutique apparaît, plus les deux aperçus.
  for (const cible of ['#apercu-logo', '#logo-boutique', '#place-logo-barre', '#place-logo-accueil']) {
    const image = $(cible);
    if (!image) continue;
    image.classList.toggle('cache', !present);
    if (present) image.src = adresse;
    else image.removeAttribute('src');
  }
  for (const vide of ['#place-vide-barre', '#place-vide-accueil']) {
    $(vide)?.classList.toggle('cache', present);
  }
}

$('#nom-boutique').addEventListener('input', (e) => {
  $('#place-nom').textContent = e.target.value.trim() || 'Borne';
});

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

/* Une matière n'est pas qu'un prix : c'est aussi la liste des tailles qu'on sait
   produire dedans, les coupes que la machine accepte, et les limites du sur-mesure.
   Tout cela vit dans un volet dépliable, pour que le tableau reste lisible. */

const deplies = new Set();

function dessinerMatieres() {
  const lignes = etat.catalogue.matieres.flatMap((m, i) => {
    normaliserMatiere(m);
    const ouvert = deplies.has(i);
    return [
      ligne(
        [
          cellule('Nom', saisie(m.nom, {
            type: 'text', maxlength: 60,
            oninput: (e) => { m.nom = e.target.value; majExemple(); },
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
          element('div', { class: 'tableau__cellule tableau__cellule--case' }, [
            element('button', {
              class: `bouton bouton--secondaire replier${ouvert ? ' replier--ouvert' : ''}`,
              type: 'button',
              onclick: () => {
                if (ouvert) deplies.delete(i); else deplies.add(i);
                dessinerMatieres();
              },
            }, [
              element('span', { class: 'replier__fleche', 'aria-hidden': 'true' }, '▸'),
              resumeMatiere(m),
            ]),
          ]),
        ],
        () => {
          if (etat.catalogue.matieres.length <= 1) {
            return afficherErreur('Il faut garder au moins une matière.');
          }
          etat.catalogue.matieres.splice(i, 1);
          deplies.clear();
          dessinerMatieres();
        },
      ),
      ouvert ? voletMatiere(m) : null,
    ].filter(Boolean);
  });
  $('#tableau-matieres').replaceChildren(...lignes);
}

/** Une entrée supprimée du catalogue disparaît des matières qui la citaient. */
function elaguer(champ, cle) {
  for (const m of etat.catalogue.matieres) {
    if (Array.isArray(m[champ])) m[champ] = m[champ].filter((x) => x !== cle);
  }
  dessinerMatieres();
}

/** Complète une matière venue d'un ancien fichier de réglages. */
function normaliserMatiere(m) {
  if (!Array.isArray(m.formats)) m.formats = [];
  if (!Array.isArray(m.formes)) m.formes = [];
  if (!m.sur_mesure) m.sur_mesure = { actif: true, min_cm: null, max_cm: null };
  if (!m.forme_libre) m.forme_libre = { actif: true, supplement: null };
}

function resumeMatiere(m) {
  const total = etat.catalogue.formats.length;
  const morceaux = [m.formats.length ? `${m.formats.length}/${total} tailles` : 'toutes tailles'];
  if (!m.decoupe) morceaux.push('sans découpe');
  else if (m.formes.length) morceaux.push(`${m.formes.length} coupes`);
  if (etat.catalogue.sur_mesure?.actif && m.sur_mesure.actif) morceaux.push('sur mesure');
  if (etat.catalogue.forme_libre?.actif && m.forme_libre.actif && m.decoupe) {
    morceaux.push('forme libre');
  }
  return element('span', {}, morceaux.join(' · '));
}

/** Cases à cocher : rien de coché veut dire « tout », et c'est ce qu'on affiche. */
function casesSousEnsemble(entrees, choisies, surChangement) {
  const tout = choisies.length === 0;
  return element('div', { class: 'cases' }, entrees.map((entree) =>
    element('label', { class: 'case' }, [
      element('input', {
        type: 'checkbox',
        checked: tout || choisies.includes(entree.cle) ? '' : null,
        onchange: (e) => {
          let suite = tout ? entrees.map((x) => x.cle) : [...choisies];
          suite = e.target.checked
            ? [...new Set([...suite, entree.cle])]
            : suite.filter((cle) => cle !== entree.cle);
          if (!suite.length) {
            e.target.checked = true;
            return afficherErreur('Gardez au moins une entrée pour cette matière.');
          }
          surChangement(suite.length === entrees.length ? [] : suite);
        },
      }),
      element('span', {}, entree.nom),
    ]),
  ));
}

function voletMatiere(m) {
  const mesureOuverte = Boolean(etat.catalogue.sur_mesure?.actif);
  const libreOuverte = Boolean(etat.catalogue.forme_libre?.actif);

  return element('div', { class: 'volet' }, [
    element('div', { class: 'volet__bloc' }, [
      element('span', { class: 'volet__titre' }, `Tailles proposées en ${m.nom || 'cette matière'}`),
      casesSousEnsemble(etat.catalogue.formats, m.formats, (suite) => {
        m.formats = suite;
        dessinerMatieres();
      }),
    ]),

    element('div', { class: 'volet__bloc' }, [
      element('span', { class: 'volet__titre' }, 'Découpe'),
      element('label', { class: 'bascule' }, [
        element('input', {
          type: 'checkbox', checked: m.decoupe ? '' : null,
          onchange: (e) => { m.decoupe = e.target.checked; dessinerMatieres(); },
        }),
        element('span', {}, 'Cette matière peut être découpée'),
      ]),
      m.decoupe
        ? casesSousEnsemble(etat.catalogue.formes, m.formes, (suite) => {
            m.formes = suite;
            dessinerMatieres();
          })
        : element('p', { class: 'choix__note' },
            'Les tirages resteront rectangulaires dans cette matière.'),
    ]),

    element('div', { class: 'volet__bloc' }, [
      element('span', { class: 'volet__titre' }, 'Sur mesure'),
      mesureOuverte
        ? element('div', {}, [
            element('label', { class: 'bascule' }, [
              element('input', {
                type: 'checkbox', checked: m.sur_mesure.actif ? '' : null,
                onchange: (e) => { m.sur_mesure.actif = e.target.checked; dessinerMatieres(); },
              }),
              element('span', {}, 'Proposer les dimensions libres pour cette matière'),
            ]),
            m.sur_mesure.actif
              ? element('div', { class: 'volet__champs' }, [
                  champLimite('Taille mini (cm)', m.sur_mesure.min_cm,
                    etat.catalogue.sur_mesure.min_cm, (v) => { m.sur_mesure.min_cm = v; }),
                  champLimite('Taille maxi (cm)', m.sur_mesure.max_cm,
                    etat.catalogue.sur_mesure.max_cm, (v) => { m.sur_mesure.max_cm = v; }),
                ])
              : null,
          ])
        : element('p', { class: 'choix__note' },
            'Le sur-mesure est coupé pour toute la boutique, plus haut dans la page.'),
    ]),

    element('div', { class: 'volet__bloc' }, [
      element('span', { class: 'volet__titre' }, 'Forme libre'),
      libreOuverte && m.decoupe
        ? element('div', {}, [
            element('label', { class: 'bascule' }, [
              element('input', {
                type: 'checkbox', checked: m.forme_libre.actif ? '' : null,
                onchange: (e) => { m.forme_libre.actif = e.target.checked; dessinerMatieres(); },
              }),
              element('span', {}, 'Laisser le client dessiner son contour'),
            ]),
            m.forme_libre.actif
              ? element('div', { class: 'volet__champs' }, [
                  champLimite('Supplément (€)', m.forme_libre.supplement,
                    etat.catalogue.forme_libre.supplement,
                    (v) => { m.forme_libre.supplement = v; }, '0.5'),
                ])
              : null,
          ])
        : element('p', { class: 'choix__note' }, m.decoupe
            ? 'La forme libre est coupée pour toute la boutique, plus haut dans la page.'
            : 'Impossible sans découpe.'),
    ]),
  ]);
}

/** Champ facultatif : laissé vide, il reprend la valeur générale de la boutique. */
function champLimite(libelle, valeur, defaut, surSaisie, pas = '1') {
  return element('label', { class: 'champ champ--court' }, [
    element('span', { class: 'champ__libelle' }, libelle),
    element('input', {
      type: 'number', min: '0', step: pas,
      value: valeur === null || valeur === undefined ? '' : valeur,
      placeholder: `${defaut} (boutique)`,
      oninput: (e) => {
        surSaisie(e.target.value === '' ? null : Number(e.target.value));
      },
    }),
  ]);
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
        const [parti] = etat.catalogue.formats.splice(i, 1);
        elaguer('formats', parti.cle);
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
        const [partie] = etat.catalogue.formes.splice(i, 1);
        elaguer('formes', partie.cle);
        dessinerFormes();
      },
    );
  });
  $('#tableau-formes').replaceChildren(...lignes);
}

$('#btn-ajout-matiere').addEventListener('click', () => {
  etat.catalogue.matieres.push({
    cle: '', nom: '', coefficient: 1, prix_m2: 0, decoupe: true,
    formats: [], formes: [],
    sur_mesure: { actif: true, min_cm: null, max_cm: null },
    forme_libre: { actif: true, supplement: null },
  });
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



/* --- options proposées au client -------------------------------------------- */

for (const id of ['#sur-mesure-actif', '#forme-libre-actif']) {
  $(id).addEventListener('change', majOptions);
}
for (const id of ['#sur-mesure-min', '#sur-mesure-max', '#forme-libre-supplement']) {
  $(id).addEventListener('input', () => {
    if (!etat) return;
    etat.catalogue.sur_mesure.min_cm = Number($('#sur-mesure-min').value);
    etat.catalogue.sur_mesure.max_cm = Number($('#sur-mesure-max').value);
    etat.catalogue.forme_libre.supplement = Number($('#forme-libre-supplement').value);
    majExempleSurMesure();
    dessinerMatieres(); // les valeurs générales servent de repère aux matières
  });
}

function majOptions() {
  $('#reglages-sur-mesure').classList.toggle('cache', !$('#sur-mesure-actif').checked);
  $('#reglages-forme-libre').classList.toggle('cache', !$('#forme-libre-actif').checked);
  if (etat) {
    etat.catalogue.sur_mesure.actif = $('#sur-mesure-actif').checked;
    etat.catalogue.forme_libre.actif = $('#forme-libre-actif').checked;
    dessinerMatieres();
  }
  majExempleSurMesure();
}

/** Le sur-mesure se facture au m² : autant le montrer noir sur blanc. */
function majExempleSurMesure() {
  if (!etat || !$('#sur-mesure-actif').checked) return;
  const matiere = etat.catalogue.matieres[0];
  const cote = Number($('#sur-mesure-max').value) || 0;
  if (!matiere || !cote) return ($('#exemple-sur-mesure').textContent = '');
  const aire = (cote / 100) * (cote / 100);
  $('#exemple-sur-mesure').replaceChildren(
    element('span', { class: 'exemple__etiquette' }, 'Exemple'),
    element('span', {}, [
      element('strong', {}, `${matiere.nom} en ${cote} × ${cote} cm`),
      ` : ${decimal(aire)} m² × ${euros(matiere.prix_m2)}/m² = `,
      element('strong', { class: 'exemple__prix' }, euros(aire * (matiere.prix_m2 || 0))),
    ]),
  );
}

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
    theme: couleurs(),
    catalogue: {
      tarification: modeActuel(),
      formes_actives: $('#formes-actives').checked,
      sur_mesure: {
        actif: $('#sur-mesure-actif').checked,
        min_cm: Number($('#sur-mesure-min').value),
        max_cm: Number($('#sur-mesure-max').value),
      },
      forme_libre: {
        actif: $('#forme-libre-actif').checked,
        supplement: Number($('#forme-libre-supplement').value),
      },
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
