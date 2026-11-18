/* Simulateur GAP : recalcule l'indice avec des poids choisis, puis une gestion mensuelle fondée sur la note sur 5.
   Même méthode que scripts/backtest_v3.py et backtest_v4_indices.py (vérifiée contre les séries Python). */
(function (root) {
  const PILIERS = ['croissance', 'infl', 'financier', 'valo', 'sentiment', 'incertitude'];

  // z-score glissant sur 120 mois (au moins 60 valeurs), borné à ±2 (comme pandas : écart-type avec n − 1)
  function zGlissant(s, win = 120, minp = 60) {
    return s.map((v, i) => {
      if (v == null) return null;
      let n = 0, sum = 0, sum2 = 0;
      for (let j = Math.max(0, i - win + 1); j <= i; j++) if (s[j] != null) { n++; sum += s[j]; sum2 += s[j] * s[j]; }
      if (n < minp) return null;
      const m = sum / n, sd = Math.sqrt(Math.max(0, (sum2 - n * m * m) / (n - 1)));
      if (!(sd > 0)) return null;
      return Math.max(-2, Math.min(2, (v - m) / sd));
    });
  }

  // rang de la valeur du mois parmi les 119 mois précédents (fenêtre de 120, au moins 60 valeurs)
  function percentile(s, win = 120, minp = 60) {
    return s.map((v, i) => {
      if (v == null) return null;
      const a = Math.max(0, i - win + 1);
      let n = 0, bas = 0;
      for (let j = a; j <= i; j++) if (s[j] != null) n++;
      if (n < minp) return null;
      for (let j = a; j < i; j++) if (s[j] != null && s[j] < v) bas++;
      return i - a === 0 ? null : bas / (i - a);
    });
  }

  const note5 = (p) => p == null ? null : Math.min(5, Math.floor(p * 5) + 1);

  const REGLES = {
    sortie1: {nom: 'Sortir du marché quand la note est à 1', expo: (n) => n > 1 ? 1 : 0},
    seuil3: {nom: 'Investir seulement quand la note est d’au moins 3', expo: (n) => n >= 3 ? 1 : 0},
    progressif: {nom: 'Exposition progressive : 0 %, 25 %, 50 %, 75 %, 100 % selon la note', expo: (n) => (n - 1) / 4},
  };

  // rows : lignes de simulation.json pour un indice, dans l'ordre des mois
  function simuler(rows, poids, partTendance = 0.5, regle = 'sortie1') {
    const lvl = rows.map((r) => {
      let num = 0, den = 0;
      for (const k of PILIERS) if (r[k] != null && poids[k] > 0) { num += r[k] * poids[k]; den += poids[k]; }
      return den > 0 ? 50 + 25 * num / den : null;
    });
    const diff3 = lvl.map((v, i) => i >= 3 && v != null && lvl[i - 3] != null ? v - lvl[i - 3] : null);
    const tz = zGlissant(diff3);
    const D = lvl.map((v, i) => v == null || tz[i] == null ? null : (1 - partTendance) * v + partTendance * (50 + 25 * tz[i]));
    const pct = percentile(D);
    const note = pct.map(note5);

    // gestion : la note de fin de mois décide de l'exposition du mois suivant ; le reste est placé au taux sans risque
    const e = REGLES[regle].expo;
    let i0 = note.findIndex((n) => n != null);
    const serie = [];
    let vs = 100, vb = 100, pics = 100, picb = 100, ddS = 0, ddB = 0, expoTot = 0;
    const rs = [], rb = [];
    for (let i = i0 + 1; i < rows.length; i++) {
      const r = rows[i];
      if (r.ret == null || note[i - 1] == null) continue;
      const x = e(note[i - 1]), cash = r.cash ?? 0;
      const rS = x * r.ret + (1 - x) * cash;
      vs *= 1 + rS; vb *= 1 + r.ret;
      pics = Math.max(pics, vs); picb = Math.max(picb, vb);
      ddS = Math.min(ddS, vs / pics - 1); ddB = Math.min(ddB, vb / picb - 1);
      expoTot += x; rs.push(rS); rb.push(r.ret);
      serie.push({mois: r.mois, strategie: vs, achat: vb, expo: x, note: note[i - 1]});
    }
    const n = serie.length;
    const vol = (a) => { const m = a.reduce((s, v) => s + v, 0) / a.length; return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1) * 12); };
    const stats = (v, dd, a) => ({final: v, tcam: Math.pow(v / 100, 12 / n) - 1, perteMax: dd, vol: vol(a)});
    const last = D.length - 1 - [...D].reverse().findIndex((v) => v != null);
    return {
      serie, D, note,
      strategie: {...stats(vs, ddS, rs), expo: expoTot / n},
      achat: {...stats(vb, ddB, rb), expo: 1},
      debut: serie[0] && serie[0].mois, fin: serie[n - 1] && serie[n - 1].mois,
      actuel: {mois: rows[last].mois, indice: D[last], note: note[last], percentile: pct[last]},
    };
  }

  const api = {PILIERS, REGLES, simuler, zGlissant, percentile};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.GapSimu = api;
})(typeof window !== 'undefined' ? window : globalThis);
