/* Symp's Kiosk — utilitaires partages par les trois pages. */

export const $ = (selecteur, racine = document) => racine.querySelector(selecteur);
export const $$ = (selecteur, racine = document) => [...racine.querySelectorAll(selecteur)];

export function element(balise, proprietes = {}, enfants = []) {
  const noeud = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(proprietes)) {
    if (cle === 'class') noeud.className = valeur;
    else if (cle === 'dataset') Object.assign(noeud.dataset, valeur);
    else if (cle.startsWith('on')) noeud.addEventListener(cle.slice(2).toLowerCase(), valeur);
    else if (valeur !== null && valeur !== undefined) noeud.setAttribute(cle, valeur);
  }
  for (const enfant of [].concat(enfants)) {
    if (enfant === null || enfant === undefined) continue;
    noeud.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return noeud;
}

export async function api(chemin, options = {}) {
  const reponse = await fetch(chemin, options);
  const type = reponse.headers.get('Content-Type') || '';
  const corps = type.includes('application/json') ? await reponse.json() : null;
  if (!reponse.ok) {
    throw new Error((corps && corps.erreur) || `Erreur ${reponse.status}`);
  }
  return corps;
}

export function poids(octets) {
  if (!octets && octets !== 0) return '';
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${(octets / 1024).toFixed(0)} Ko`;
  return `${(octets / (1024 * 1024)).toFixed(1)} Mo`;
}

export function heure(horodatage) {
  return new Date(horodatage * 1000).toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ilYA(horodatage) {
  const secondes = Math.max(0, Math.round(Date.now() / 1000 - horodatage));
  if (secondes < 60) return "a l'instant";
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const heures = Math.round(minutes / 60);
  return `il y a ${heures} h`;
}

export function estAffichable(mime) {
  return ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'].includes(mime);
}

export function extension(mime) {
  return (mime.split('/')[1] || 'fichier').toUpperCase();
}

/**
 * Reconnexion automatique geree par le navigateur ; on ne fait qu'ecouter.
 * Avec un jeton, on ne recoit que les evenements de cette session.
 */
export function ecouterEvenements(gestionnaires, jeton = null) {
  const adresse = jeton ? `/api/evenements?session=${encodeURIComponent(jeton)}` : '/api/evenements';
  const source = new EventSource(adresse);
  for (const [nom, gestionnaire] of Object.entries(gestionnaires)) {
    source.addEventListener(nom, (evenement) => {
      let donnees = null;
      try {
        donnees = JSON.parse(evenement.data);
      } catch (erreur) {
        donnees = null;
      }
      gestionnaire(donnees);
    });
  }
  return source;
}

export function marquerPageActive() {
  const courant = window.location.pathname.replace(/\/$/, '') || '/';
  for (const lien of $$('.navigation a')) {
    const cible = new URL(lien.href).pathname.replace(/\/$/, '') || '/';
    if (cible === courant) lien.setAttribute('aria-current', 'page');
  }
}

export async function config() {
  if (!config._promesse) config._promesse = api('/api/config');
  return config._promesse;
}

export async function catalogue() {
  if (!catalogue._promesse) catalogue._promesse = api('/api/catalogue');
  return catalogue._promesse;
}

export function prixLisible(montant, devise = '€') {
  return `${Number(montant).toFixed(2).replace('.', ',')} ${devise}`;
}
