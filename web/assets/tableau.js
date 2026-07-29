/* Tableau de bord du PC : les chiffres du jour, les files d'attente, la tendance. */

import {
  $, api, ecouterEvenements, element, heure, ilYA, prixLisible,
} from './commun.js';

import { brancherChangementDePoste, poserNavigation } from './navigation.js';

let devise = '€';

demarrer();

async function demarrer() {
  await poserNavigation();
  await charger();
  // Le tableau suit la boutique en direct : un encaissement au comptoir se voit
  // ici sans rafraîchir la page.
  ecouterEvenements({
    depot: charger, paiement: charger, suppression: charger,
    purge: charger, reglages: charger,
  });
  setInterval(charger, 60_000); // les délais d'expiration avancent tout seuls
}

async function charger() {
  try {
    dessiner(await api('/api/tableau'));
    $('#message-erreur').classList.add('cache');
  } catch (echec) {
    $('#message-erreur').textContent = `Chiffres indisponibles : ${echec.message}`;
    $('#message-erreur').classList.remove('cache');
  }
}

function dessiner(donnees) {
  devise = donnees.devise || '€';
  const jour = donnees.jour;

  $('#horodatage').textContent = `à jour à ${heure(donnees.maintenant)}`;
  if (donnees.boutique?.nom) $('#nom-boutique').textContent = donnees.boutique.nom;

  tuiles([
    { etiquette: 'Encaissé aujourd\'hui', valeur: prixLisible(jour.encaisse, devise), fort: true },
    {
      etiquette: 'En attente de paiement',
      valeur: prixLisible(jour.attente, devise),
      note: donnees.a_encaisser.length
        ? `${donnees.a_encaisser.length} dépôt${donnees.a_encaisser.length > 1 ? 's' : ''}`
        : 'rien à réclamer',
      alerte: jour.attente > 0,
    },
    {
      etiquette: 'Dépôts du jour',
      valeur: String(jour.depots),
      note: `${jour.tirages} tirage${jour.tirages > 1 ? 's' : ''}`,
    },
    { etiquette: 'Panier moyen', valeur: prixLisible(jour.panier_moyen, devise) },
  ]);

  file('encaisser', donnees.a_encaisser);
  file('expirent', donnees.expirent);
  histogramme(donnees.jours);
  classement('#classement-supports', donnees.supports);
  classement('#classement-formats', donnees.formats);
  listePostes(donnees.postes);
}

function tuiles(entrees) {
  $('#tuiles').replaceChildren(...entrees.map((t) =>
    element('div', { class: `tuile${t.fort ? ' tuile--forte' : ''}` }, [
      element('span', { class: 'tuile__etiquette' }, t.etiquette),
      element('strong', { class: 'tuile__valeur' }, t.valeur),
      t.note
        ? element('span', { class: `tuile__note${t.alerte ? ' tuile__note--alerte' : ''}` }, t.note)
        : null,
    ].filter(Boolean)),
  ));
}

function file(nom, lignes) {
  $(`#compte-${nom}`).replaceChildren(
    element('span', { class: 'etat__point' }),
    document.createTextNode(` ${lignes.length}`),
  );
  $(`#vide-${nom}`).classList.toggle('cache', lignes.length > 0);
  $(`#liste-${nom}`).replaceChildren(...lignes.map((d) => ligneDepot(d, nom)));
}

function ligneDepot(depot, nom) {
  const detail = nom === 'expirent'
    ? `expire ${quandExpire(depot.expires_at)}`
    : `validé ${ilYA(depot.validated_at)}`;

  return element('li', {}, element('a', {
    class: 'depot', href: `/recuperer?code=${depot.code}`,
  }, [
    element('span', { class: 'depot__code' }, depot.code),
    element('span', { class: 'depot__infos' }, [
      element('span', { class: 'depot__titre' },
        `${depot.tirages} tirage${depot.tirages > 1 ? 's' : ''} · ${prixLisible(depot.total, devise)}`),
      element('span', { class: 'depot__meta' }, detail),
    ]),
    depot.apercu
      ? element('span', { class: 'depot__apercus' },
          element('img', { src: `/media/${depot.apercu}`, alt: '', loading: 'lazy' }))
      : null,
  ].filter(Boolean)));
}

function quandExpire(horodatage) {
  const minutes = Math.round((horodatage * 1000 - Date.now()) / 60000);
  if (minutes <= 0) return 'maintenant';
  if (minutes < 60) return `dans ${minutes} min`;
  return `dans ${Math.round(minutes / 60)} h`;
}

/** Histogramme en barres CSS : pas de bibliothèque, pas de canvas. */
function histogramme(jours) {
  const sommet = Math.max(1, ...jours.map((j) => j.encaisse));
  $('#histogramme').replaceChildren(...jours.map((j, i) => {
    const dernier = i === jours.length - 1;
    return element('div', { class: `histo__jour${dernier ? ' histo__jour--aujourdhui' : ''}` }, [
      element('span', { class: 'histo__valeur' }, j.encaisse ? prixLisible(j.encaisse, devise) : ''),
      element('div', {
        class: 'histo__barre',
        style: `height: ${Math.round((j.encaisse / sommet) * 100)}%`,
        title: `${j.depots} dépôt(s)`,
      }),
      element('span', { class: 'histo__nom' }, dernier ? "auj." : j.libelle),
    ]);
  }));
}

function classement(cible, entrees) {
  if (!entrees.length) {
    return void $(cible).replaceChildren(
      element('li', { class: 'classement__vide' }, 'Aucune vente enregistrée.'),
    );
  }
  const sommet = Math.max(...entrees.map((e) => e.tirages));
  $(cible).replaceChildren(...entrees.map((e) =>
    element('li', { class: 'classement__ligne' }, [
      element('span', { class: 'classement__nom' }, e.nom),
      element('span', { class: 'classement__jauge' },
        element('span', {
          class: 'classement__part',
          style: `width: ${Math.round((e.tirages / sommet) * 100)}%`,
        })),
      element('span', { class: 'classement__chiffre' },
        `${e.tirages} · ${prixLisible(e.recette, devise)}`),
    ]),
  ));
}

function listePostes(postes) {
  const inscrits = postes.inscrits || {};
  $('#resume-postes').textContent = Object.entries(inscrits)
    .map(([role, nombre]) => `${nombre} ${role}`)
    .join(' · ');

  const connectes = postes.connectes || [];
  if (!connectes.length) {
    return void $('#liste-postes').replaceChildren(
      element('li', { class: 'classement__vide' }, 'Aucun poste actif en ce moment.'),
    );
  }
  $('#liste-postes').replaceChildren(...connectes.map((p) =>
    element('li', { class: 'poste' }, [
      element('span', { class: 'pastille' }, [
        element('span', { class: 'pastille__point' }),
        p.role,
      ]),
      element('span', { class: 'poste__meta' }, `vu ${ilYA(p.vu_le)}`),
    ]),
  ));
}

brancherChangementDePoste();
