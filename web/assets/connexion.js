/* Lancement : abonnement de la boutique, puis rôle de cet appareil.
 *
 * L'abonnement ne se saisit qu'une fois, sur la machine qui héberge
 * l'application. Les autres appareils arrivent par le réseau local et n'ont
 * qu'une chose à déclarer : ce qu'ils sont.
 */

import { $, api, element } from './commun.js';

const erreur = $('#message-erreur');

const LIBELLES = {
  expiree: {
    titre: 'Abonnement expiré',
    detail: "Votre abonnement Symp's Kiosk est arrivé à échéance. Renouvelez-le, "
      + 'puis réessayez depuis cette machine.',
  },
  grace: {
    titre: 'Connexion à vérifier',
    detail: "Cette machine n'a pas pu joindre le serveur d'abonnement depuis un "
      + 'moment. Rétablissez la connexion Internet, puis réessayez.',
  },
  alteree: {
    titre: 'Licence illisible',
    detail: 'Le fichier de licence de cette machine est invalide. Reconnectez-vous '
      + 'pour en obtenir un nouveau.',
  },
};

// Trois silhouettes distinctes : un totem vertical, une imprimante, un écran large.
const ICONES = {
  borne: 'M15 4h18v32H15zM19 44h10M24 36v8',
  imprimante: 'M12 18V6h24v12M12 30h24v12H12zM6 18h36v12H6z',
  pc: 'M4 9h40v24H4zM18 43h12M24 33v10',
};

let roles = [];
let premiere = false; // l'appareil qui vient d'activer l'abonnement

demarrer();

async function demarrer() {
  try {
    const reglages = await api('/api/config');
    $('#version').textContent = reglages.version || '—';
  } catch (echec) {
    /* la page doit rester utilisable même si la configuration ne répond pas */
  }

  let compte = null;
  try {
    compte = await api('/api/compte');
  } catch (echec) {
    return; // on laisse le formulaire de connexion
  }

  if (compte.utilisable) return void demanderRole();
  if (compte.etat && LIBELLES[compte.etat]) montrerProbleme(compte);
}

/* --- rôle de l'appareil ------------------------------------------------------ */

async function demanderRole() {
  let poste = null;
  try {
    poste = await api('/api/poste');
  } catch (echec) {
    return void (window.location.href = '/');
  }

  // Rôle déjà connu : on file à l'écran de cet appareil.
  if (poste.role) return void (window.location.href = poste.accueil || '/');

  roles = poste.roles || [];
  $('#etape-connexion').classList.add('cache');
  $('#etape-probleme').classList.add('cache');
  $('#etape-role').classList.remove('cache');
  // Trois cartes côte à côte demandent plus de place que le formulaire.
  document.querySelector('.enveloppe').classList.add('enveloppe--roles');

  if (premiere) {
    $('#titre-role').textContent = 'Cette machine est…';
    $('#chapeau-role').textContent =
      "C'est elle qui héberge l'application et garde les photos. Les autres "
      + 'appareils de la boutique choisiront leur rôle en arrivant, sans rien saisir.';
    $('#btn-tous-roles').classList.remove('cache');
  }
  dessinerRoles();
}

function dessinerRoles() {
  // Au premier lancement, la machine hôte est le PC ou l'imprimante : la borne
  // n'est proposée qu'à la demande, pour ne bloquer personne.
  const montres = premiere ? roles.filter((r) => r.cle !== 'borne') : roles;

  $('#liste-roles').replaceChildren(...montres.map((role) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 48 48');
    svg.setAttribute('class', 'role__icone');
    svg.setAttribute('aria-hidden', 'true');
    const chemin = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chemin.setAttribute('d', ICONES[role.cle] || ICONES.pc);
    svg.append(chemin);

    return element('button', {
      class: 'role', type: 'button', dataset: { cle: role.cle },
      onclick: () => choisir(role.cle),
    }, [
      svg,
      element('span', { class: 'role__nom' }, role.nom),
      element('span', { class: 'role__resume' }, role.resume),
    ]);
  }));
}

$('#btn-tous-roles').addEventListener('click', () => {
  premiere = false;
  $('#btn-tous-roles').classList.add('cache');
  dessinerRoles();
});

async function choisir(cle) {
  for (const bouton of document.querySelectorAll('.role')) bouton.disabled = true;
  try {
    const poste = await api('/api/poste', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: cle }),
    });
    window.location.href = poste.accueil || '/';
  } catch (echec) {
    $('#erreur-role').textContent = echec.message;
    $('#erreur-role').classList.remove('cache');
    for (const bouton of document.querySelectorAll('.role')) bouton.disabled = false;
  }
}

/* --- abonnement -------------------------------------------------------------- */

function montrerProbleme(compte) {
  const { titre, detail } = LIBELLES[compte.etat];
  $('#titre-probleme').textContent = titre;
  $('#detail-probleme').textContent = compte.email ? `${detail} (${compte.email})` : detail;
  $('#etape-connexion').classList.add('cache');
  $('#etape-probleme').classList.remove('cache');
}

$('#btn-reessayer').addEventListener('click', () => window.location.reload());

$('#btn-changer').addEventListener('click', async () => {
  try {
    await api('/api/compte/deconnexion', { method: 'POST' });
  } catch (echec) {
    /* sans importance : on revient au formulaire dans tous les cas */
  }
  $('#etape-probleme').classList.add('cache');
  $('#etape-connexion').classList.remove('cache');
});

$('#formulaire').addEventListener('submit', async (evenement) => {
  evenement.preventDefault();
  const bouton = $('#btn-connexion');
  erreur.classList.add('cache');
  bouton.disabled = true;
  bouton.textContent = 'Connexion…';

  try {
    await api('/api/compte/connexion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: $('#email').value.trim(),
        mot_de_passe: $('#mot-de-passe').value,
      }),
    });
    premiere = true;
    demanderRole();
  } catch (echec) {
    erreur.textContent = echec.message;
    erreur.classList.remove('cache');
    bouton.disabled = false;
    bouton.textContent = 'Se connecter';
    $('#mot-de-passe').select();
  }
});
