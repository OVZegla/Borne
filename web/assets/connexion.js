/* Écran de connexion : active l'abonnement sur cette machine. */

import { $, api } from './commun.js';

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

  if (compte.utilisable) return void (window.location.href = '/');
  if (compte.etat && LIBELLES[compte.etat]) montrerProbleme(compte);
}

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
    window.location.href = '/';
  } catch (echec) {
    erreur.textContent = echec.message;
    erreur.classList.remove('cache');
    bouton.disabled = false;
    bouton.textContent = 'Se connecter';
    $('#mot-de-passe').select();
  }
});
