/* Roue chromatique, sans aucune dependance.
 *
 * Le selecteur natif `<input type="color">` ouvre une fenetre differente sur
 * chaque systeme, et sur une borne tactile il est souvent inutilisable. On
 * dessine donc notre propre roue : teinte sur le tour, saturation du centre
 * vers le bord, luminosite sur un curseur a cote.
 */

const TAILLE = 200; // cote du disque, en pixels de la toile

/* --- conversions ----------------------------------------------------------- */

export function versRvb(h, s, v) {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  const [r, g, b] = h < 60 ? [c, x, 0]
    : h < 120 ? [x, c, 0]
    : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c]
    : h < 300 ? [x, 0, c]
    : [c, 0, x];
  return [r, g, b].map((canal) => Math.round((canal + m) * 255));
}

export function versHexa(h, s, v) {
  return `#${versRvb(h, s, v).map((n) => n.toString(16).padStart(2, '0')).join('')}`.toUpperCase();
}

export function depuisHexa(hexa) {
  const propre = String(hexa || '').trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(propre)) return null;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(propre.slice(i, i + 2), 16) / 255);
  const maxi = Math.max(r, g, b);
  const mini = Math.min(r, g, b);
  const ecart = maxi - mini;

  let teinte = 0;
  if (ecart !== 0) {
    if (maxi === r) teinte = 60 * (((g - b) / ecart) % 6);
    else if (maxi === g) teinte = 60 * ((b - r) / ecart + 2);
    else teinte = 60 * ((r - g) / ecart + 4);
  }
  return [(teinte + 360) % 360, maxi === 0 ? 0 : ecart / maxi, maxi];
}

/* --- composant -------------------------------------------------------------- */

/**
 * Installe une roue dans `hote` et renvoie de quoi la piloter.
 * `onChange` recoit la couleur en #RRGGBB a chaque mouvement.
 */
export function creerRoue(hote, { valeur = '#00287E', onChange = () => {} } = {}) {
  let [teinte, saturation, lumiere] = depuisHexa(valeur) || [217, 1, 0.49];

  const toile = document.createElement('canvas');
  toile.width = TAILLE;
  toile.height = TAILLE;
  toile.className = 'roue__toile';
  toile.setAttribute('role', 'application');
  toile.setAttribute('aria-label', 'Roue chromatique');

  const curseur = document.createElement('span');
  curseur.className = 'roue__curseur';

  const disque = document.createElement('div');
  disque.className = 'roue__disque';
  disque.append(toile, curseur);

  const pastille = document.createElement('span');
  pastille.className = 'roue__pastille';

  const lumineux = document.createElement('input');
  lumineux.type = 'range';
  lumineux.min = '2';
  lumineux.max = '100';
  lumineux.className = 'roue__lumiere';
  lumineux.setAttribute('aria-label', 'Luminosité');

  const hexa = document.createElement('input');
  hexa.type = 'text';
  hexa.maxLength = 7;
  hexa.spellcheck = false;
  hexa.className = 'roue__hex';
  hexa.setAttribute('aria-label', 'Code couleur');

  const reglages = document.createElement('div');
  reglages.className = 'roue__reglages';
  reglages.append(pastille, lumineux, hexa);

  const cadre = document.createElement('div');
  cadre.className = 'roue';
  cadre.append(disque, reglages);
  hote.append(cadre);

  const contexte = toile.getContext('2d');
  const rayon = TAILLE / 2;

  function peindre() {
    const image = contexte.createImageData(TAILLE, TAILLE);
    for (let y = 0; y < TAILLE; y += 1) {
      for (let x = 0; x < TAILLE; x += 1) {
        const dx = x - rayon + 0.5;
        const dy = y - rayon + 0.5;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const indice = (y * TAILLE + x) * 4;
        if (distance > rayon) continue; // hors du disque : transparent
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        const [r, g, b] = versRvb((angle + 360) % 360, Math.min(1, distance / rayon), lumiere);
        image.data[indice] = r;
        image.data[indice + 1] = g;
        image.data[indice + 2] = b;
        // Bord adouci : sans cela le disque parait cranele.
        image.data[indice + 3] = Math.round(255 * Math.min(1, rayon - distance));
      }
    }
    contexte.putImageData(image, 0, 0);
  }

  function placerCurseur() {
    const angle = (teinte * Math.PI) / 180;
    curseur.style.left = `${50 + Math.cos(angle) * saturation * 50}%`;
    curseur.style.top = `${50 + Math.sin(angle) * saturation * 50}%`;
    curseur.style.background = versHexa(teinte, saturation, lumiere);
  }

  function rafraichir(prevenir = true) {
    const couleur = versHexa(teinte, saturation, lumiere);
    pastille.style.background = couleur;
    lumineux.value = String(Math.round(lumiere * 100));
    lumineux.style.setProperty('--vif', versHexa(teinte, saturation, 1));
    if (document.activeElement !== hexa) hexa.value = couleur;
    placerCurseur();
    if (prevenir) onChange(couleur);
  }

  function viser(evenement) {
    const boite = toile.getBoundingClientRect();
    const dx = evenement.clientX - boite.left - boite.width / 2;
    const dy = evenement.clientY - boite.top - boite.height / 2;
    teinte = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
    saturation = Math.min(1, Math.sqrt(dx * dx + dy * dy) / (boite.width / 2));
    rafraichir();
  }

  let tire = false;
  toile.addEventListener('pointerdown', (e) => {
    tire = true;
    toile.setPointerCapture(e.pointerId);
    viser(e);
  });
  toile.addEventListener('pointermove', (e) => { if (tire) viser(e); });
  toile.addEventListener('pointerup', () => { tire = false; });
  toile.addEventListener('pointercancel', () => { tire = false; });

  lumineux.addEventListener('input', () => {
    lumiere = Number(lumineux.value) / 100;
    peindre();
    rafraichir();
  });

  hexa.addEventListener('input', () => {
    const lu = depuisHexa(hexa.value);
    if (!lu) return;
    [teinte, saturation, lumiere] = lu;
    peindre();
    rafraichir();
  });
  hexa.addEventListener('blur', () => { if (!depuisHexa(hexa.value)) rafraichir(false); });

  peindre();
  rafraichir(false);

  return {
    valeur: () => versHexa(teinte, saturation, lumiere),
    definir(couleur, prevenir = false) {
      const lu = depuisHexa(couleur);
      if (!lu) return;
      [teinte, saturation, lumiere] = lu;
      peindre();
      rafraichir(prevenir);
    },
  };
}
