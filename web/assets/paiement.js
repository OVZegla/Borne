/* Page de règlement, ouverte sur le téléphone après scan du QR de paiement. */

import { $, api, ecouterEvenements, element, prixLisible } from './commun.js';

const jeton = new URLSearchParams(window.location.search).get('j');
const erreur = $('#message-erreur');

let commande = null;

demarrer();

async function demarrer() {
  if (!jeton) return echouer('Lien incomplet. Scannez à nouveau le QR code de paiement.');
  try {
    commande = await api(`/api/paiement/${jeton}`);
  } catch (echec) {
    return echouer('Commande introuvable ou expirée. Rapprochez-vous de la borne.');
  }
  afficher();
}

function afficher() {
  if (commande.paiement === 'paye') return afficherPayee();

  $('#liste-articles').replaceChildren(
    ...commande.articles.map((article) =>
      element('li', { class: 'recap__ligne' }, [
        element('span', { class: 'recap__nom' }, article.nom),
        element('span', { class: 'recap__detail' }, article.libelle),
        element('span', { class: 'recap__prix' }, prixLisible(article.prix, commande.devise)),
      ]),
    ),
  );
  $('#total').textContent = prixLisible(commande.total, commande.devise);

  // La boutique peut envoyer ses clients vers son propre moyen de paiement.
  const config = commande.config || {};
  if (config.mode === 'lien' && config.lien) {
    $('#lien-externe').href = config.lien;
    $('#lien-externe').textContent = config.libelle || 'Payer maintenant';
    $('#bloc-externe').classList.remove('cache');
  }

  majEtat();
  $('#etape-commande').classList.remove('cache');

  // La boutique confirme l'encaissement de son côté : on suit en direct.
  ecouterEvenements({
    paiement: (donnees) => {
      if (donnees?.paiement !== 'paye') return;
      commande = { ...commande, ...donnees };
      afficherPayee();
    },
  }, jeton);
}

function majEtat() {
  const boite = $('#etat-commande');
  if (!boite) return;
  const paye = commande.paiement === 'paye';
  boite.className = `etat ${paye ? 'etat--paye' : 'etat--attente'}`;
  boite.replaceChildren(
    element('span', { class: 'etat__point' }),
    document.createTextNode(paye ? ' Réglé' : ' En attente de règlement'),
  );
}

function afficherPayee() {
  const nombre = commande.articles.length;
  $('#resume-paye').textContent =
    `${nombre} ${nombre > 1 ? 'tirages' : 'tirage'} · ` +
    `${prixLisible(commande.total, commande.devise)} réglés.`;
  $('#etape-commande').classList.add('cache');
  $('#etape-payee').classList.remove('cache');
}

function echouer(texte) {
  erreur.textContent = texte;
  erreur.classList.remove('cache');
}
