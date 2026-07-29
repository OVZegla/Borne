/* Barre de navigation des postes de la boutique.
 *
 * Chaque appareil ne voit que les pages auxquelles son rôle donne droit : la
 * borne n'a pas de navigation du tout, l'imprimante voit la réception et les
 * réglages, le PC ajoute le tableau de bord. Le serveur applique les mêmes
 * règles de son côté — ceci n'est que le menu.
 */

import { $, api, element } from './commun.js';

const ENTREES = [
  { droit: 'tableau', href: '/tableau', nom: 'Tableau de bord' },
  { droit: 'reception', href: '/recuperer', nom: 'Réception' },
  { droit: 'reglages', href: '/reglages', nom: 'Réglages' },
];

export async function poserNavigation() {
  let poste = null;
  try {
    poste = await api('/api/poste');
  } catch (echec) {
    return null;
  }
  if (!poste.role) {
    window.location.href = '/connexion';
    return null;
  }

  const barre = $('#navigation');
  if (barre) {
    const courant = window.location.pathname.replace(/\/$/, '') || '/';
    barre.replaceChildren(...ENTREES
      .filter((e) => poste.droits.includes(e.droit))
      .map((e) => element('a', {
        href: e.href,
        'aria-current': e.href === courant ? 'page' : null,
      }, e.nom)));
  }

  const pied = $('#pied-poste');
  if (pied) pied.textContent = `poste « ${poste.nom} »`;

  return poste;
}

/** Bouton « changer le rôle de cet appareil », commun aux pages de gestion. */
export function brancherChangementDePoste(selecteur = '#btn-changer-poste') {
  const bouton = $(selecteur);
  if (!bouton) return;
  bouton.addEventListener('click', async () => {
    if (!window.confirm('Cet appareil redemandera son rôle au prochain chargement. Continuer ?')) return;
    try {
      await api('/api/poste', { method: 'DELETE' });
    } catch (echec) { /* on part quand même vers l'écran de choix */ }
    window.location.href = '/connexion';
  });
}
