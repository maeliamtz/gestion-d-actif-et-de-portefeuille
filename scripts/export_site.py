"""Exporte les données de l'appli GAP pour les 3 indices (S&P 500, CAC 40, MSCI World)."""
import json, math, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest_v3 as us
import backtest_v4_indices as mi

OUT = os.path.join(HERE, "..", "site", "data"); os.makedirs(OUT, exist_ok=True)
CODE = [{"label": n, "value": open(os.path.join(HERE, n)).read(), "type": "code", "lang": "python"}
        for n in ["export_site.py", "backtest_v3.py", "backtest_v4_indices.py"]]
META = CODE + [{"label": "Données", "value": (
    "FRED (US : BAA10Y, UNRATE, FEDFUNDS, PCEPILFE, DTWEXBGS/TWEXBMTH, USEPUINDXM, USALOLITOAASTSAM, TB3MS ; "
    "zone euro : DEULOLITOAASTSAM, FRALOLITOAASTSAM, LRHUTTTTFRM156S, LRHUTTTTDEM156S, CP0000EZ19M086NEST, ECBDFR, "
    "IRSTCI01EZM156N, IRLTLT01DEM156N, DEXUSEU, CCUSMA02EZM618N, EUEPUINDXM ; Chine : CHNLOLITOAASTSAM), "
    "MSCI (MSCI World prix et dividendes réinvestis, USD), Yahoo Finance (CAC 40), multpl.com (bénéfices S&P 500), "
    "Shiller, VIX CBOE, Brent EIA. Mise à jour automatique chaque mois.")}]
LAST = us.FIN; PREV = LAST - pd.DateOffset(months=3)

def clean(v):
    if isinstance(v, (float, np.floating)): return None if not math.isfinite(v) else round(float(v), 4)
    return v
def dump(name, rows):
    rows = [{k: clean(v) for k, v in r.items()} for r in rows]
    json.dump({"rows": rows, "meta": META}, open(f"{OUT}/{name}.json", "w"), ensure_ascii=False); print(name, len(rows))
zname = lambda p: None if not np.isfinite(p) else ("prudence" if p <= .2 else "favorable" if p > .8 else "neutre")

# séries par indice : (indice D, percentile, prix, piliers)
pct_sp = us.pct_rank(us.idx_v2c)
SER = {"S&P 500": dict(D=us.idx_v2c, pct=pct_sp, prix=us.price,
                       P=us.P.rename(columns={"infl_v2": "infl"})[["croissance", "infl", "financier", "valo", "sentiment", "incertitude"]]),
       "CAC 40": dict(D=mi.OUT["CAC 40"]["D"], pct=mi.OUT["CAC 40"]["pct"], prix=mi.OUT["CAC 40"]["prix"], P=mi.OUT["CAC 40"]["P"]),
       "MSCI World": dict(D=mi.OUT["MSCI World"]["D"], pct=mi.OUT["MSCI World"]["pct"], prix=mi.OUT["MSCI World"]["prix"],
                          P=mi.OUT["MSCI World"]["P"])}

# 1. historique
h = []
for nom, s in SER.items():
    for d in s["D"].loc["1996-01-01":LAST].dropna().index:
        p = s["pct"][d]
        h.append({"indice_nom": nom, "mois": d.strftime("%Y-%m"), "indice": s["D"][d],
                  "percentile": p * 100 if np.isfinite(p) else None, "zone": zname(p), "prix": s["prix"][d]})
dump("historique", h)

# 2. piliers
DESC = {
    "S&P 500": {"croissance": "Indicateur avancé OCDE US, chômage US", "infl": "Core PCE vs 2 %, hausse des Fed funds",
                "financier": "Écart de crédit Baa, dollar large, Brent", "valo": "Rendement des bénéfices − taux 10 ans (garde-fou, hors score)",
                "sentiment": "VIX, momentum du S&P 500", "incertitude": "Incertitude politique US (EPU)"},
    "CAC 40": {"croissance": "Indicateurs avancés OCDE (Allemagne/France 65 %, US 20 %, Chine 15 %), chômage",
               "infl": "Inflation zone euro et taux BCE (65 %), Core PCE et Fed (20 %)",
               "financier": "Écart de crédit Baa, Brent, euro (un euro faible aide le CAC 40)",
               "valo": "Non disponible (pas d'historique gratuit du PER du CAC 40)",
               "sentiment": "VIX (VSTOXX indisponible), momentum du CAC 40", "incertitude": "EPU Europe (65 %) et US (20 %)"},
    "MSCI World": {"croissance": "Indicateurs avancés OCDE (US 70 %, Allemagne/France 20 %, Chine 10 %), chômage",
                   "infl": "Core PCE et Fed (70 %), inflation zone euro et BCE (20 %)",
                   "financier": "Écart de crédit Baa, dollar large, Brent",
                   "valo": "Non disponible (pas d'historique gratuit du PER du MSCI World)",
                   "sentiment": "VIX, momentum du MSCI World", "incertitude": "EPU US (70 %) et Europe (20 %)"}}
NOMS = [("croissance", "Croissance", 25), ("infl", "Inflation et banques centrales", 15), ("financier", "Conditions financières", 20),
        ("valo", "Valorisation", 15), ("sentiment", "Sentiment et tendance", 15), ("incertitude", "Géopolitique et incertitude", 10)]
rows = []
for nom, s in SER.items():
    P = s["P"]
    for col, lib, poids in NOMS:
        sc = P[col][LAST] if col in P else np.nan; sp = P[col][PREV] if col in P else np.nan
        rows.append({"indice_nom": nom, "pilier": lib, "poids": poids, "score": sc, "score_3m": sp,
                     "variation_3m": sc - sp if np.isfinite(sc) and np.isfinite(sp) else None,
                     "dans_le_score": "non (garde-fou)" if col == "valo" and np.isfinite(sc) else ("non (indisponible)" if not np.isfinite(sc) else "oui"),
                     "indicateurs": DESC[nom][col]})
dump("piliers", rows)

# 3. indicateurs (dernière valeur), toutes zones
LIB = [("g_us_cli", "Indicateur avancé OCDE US, variation 3 mois", "États-Unis", "pt", 1),
       ("g_us_chom", "Chômage US, variation 6 mois", "États-Unis", "pt", -1),
       ("g_ez_cli", "Indicateur avancé OCDE Allemagne/France, variation 3 mois", "Zone euro", "pt", 1),
       ("g_ez_chom", "Chômage Allemagne/France, variation 6 mois", "Zone euro", "pt", -1),
       ("g_cn_cli", "Indicateur avancé OCDE Chine, variation 3 mois", "Chine", "pt", 1),
       ("i_us_pce", "Écart du Core PCE à 2 %", "États-Unis", "pt", -1),
       ("i_us_taux", "Hausse des Fed funds sur 6 mois", "États-Unis", "pt", -1),
       ("i_ez_hicp", "Écart de l'inflation zone euro à 2 %", "Zone euro", "pt", -1),
       ("i_ez_taux", "Hausse du taux BCE sur 6 mois", "Zone euro", "pt", -1),
       ("f_credit", "Écart de crédit Baa − 10 ans", "Monde", "pt", -1),
       ("f_usd", "Dollar large, variation 6 mois", "Monde", "%", -100),
       ("f_eur_faible", "Euro/dollar, variation 6 mois", "Zone euro", "%", -100),
       ("f_oil", "Brent, variation 6 mois", "Monde", "%", -100),
       ("s_vix", "VIX (moyenne du mois)", "Monde", "pts", -1),
       ("s_mom_cac", "Momentum CAC 40 (12-1 mois)", "Zone euro", "%", 100),
       ("s_mom_msci", "Momentum MSCI World (12-1 mois)", "Monde", "%", 100),
       ("u_us_epu", "Incertitude politique US (EPU)", "États-Unis", "pts", -1),
       ("u_ez_epu", "Incertitude politique Europe (EPU)", "Zone euro", "pts", -1)]
rows = [{"indicateur": "Momentum S&P 500 (12-1 mois)", "zone_geo": "États-Unis", "valeur": us.ind["s_mom"][LAST] * 100, "unite": "%",
         "score_z": us.Z["s_mom"][LAST], "mois": LAST.strftime("%Y-%m")},
        {"indicateur": "Prime de risque S&P 500 (bénéfices − 10 ans)", "zone_geo": "États-Unis", "valeur": us.ind["v_erp"][LAST], "unite": "pt",
         "score_z": us.Z["v_erp"][LAST], "mois": LAST.strftime("%Y-%m")}]
for k, lib, zg, u, mult in LIB:
    lv = mi.I[k].loc[:LAST].last_valid_index()
    rows.append({"indicateur": lib, "zone_geo": zg, "valeur": mi.I[k][lv] * mult, "unite": u, "score_z": mi.Z[k][lv], "mois": lv.strftime("%Y-%m")})
dump("indicateurs", rows)

# 4. backtest
rows = []
for v, r in us.res.iterrows():
    rows.append({"indice_nom": "S&P 500", "variante": v, "periode": f"1991-{us.end[:4]}", "corr_12m": r.get("c12"), "corr_2008_2025": r.get("c12_0825"),
                 "tcam_pct": r["tcam"] * 100, "perte_max_pct": r["perte_max"] * 100, "temps_investi_pct": r["investi"] * 100})
for nom, R in mi.RES.items():
    per = mi.CFG[nom]["start"][:4] + "-" + us.end[:4]
    for v, r in R.iterrows():
        rows.append({"indice_nom": nom, "variante": v, "periode": per, "corr_12m": r["corr_12m"], "corr_2008_2025": r["corr_2008_2025"],
                     "tcam_pct": r["tcam"] * 100, "perte_max_pct": r["perte_max"] * 100, "temps_investi_pct": r["investi"] * 100})
    r = R.iloc[0]
    rows.append({"indice_nom": nom, "variante": "Achat-conservation", "periode": per, "corr_12m": None, "corr_2008_2025": None,
                 "tcam_pct": r["tcam_bh"] * 100, "perte_max_pct": r["perte_max_bh"] * 100, "temps_investi_pct": 100.0})
dump("backtest", rows)

# 5. date de mise à jour et sources en échec
maj = os.path.join(HERE, "..", "data", "maj.json")
info = json.load(open(maj)) if os.path.exists(maj) else {"date": None, "erreurs": []}
json.dump({"rows": [{"mise_a_jour": info.get("date"), "dernier_mois": LAST.strftime("%Y-%m"),
                     "sources_en_echec": "; ".join(info.get("erreurs") or []) or "aucune"}], "meta": META},
          open(f"{OUT}/maj.json", "w"), ensure_ascii=False)
