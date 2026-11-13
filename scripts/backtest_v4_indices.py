"""Backtest v4 : indice GAP pour le CAC 40 et le MSCI World (pondération des zones US / zone euro / Chine)."""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_v3 as us                       # S&P 500 et données US (FRED, VIX, Brent, momentum...)
D = us.D
idx = us.idx
z, pct_rank = us.z, us.pct_rank

eu = pd.read_csv(f"{D}/fred_eu_cn.csv").set_index("mois"); eu.index = pd.to_datetime(eu.index + "-01"); eu = eu.reindex(idx)
cac = pd.read_csv(f"{D}/cac40.csv").set_index("mois"); cac.index = pd.to_datetime(cac.index + "-01")
cac = cac["cac40"].reindex(idx)
ms = pd.read_csv(f"{D}/msci_world.csv").set_index("mois"); ms.index = pd.to_datetime(ms.index + "-01"); ms = ms.reindex(idx)

# rendements totaux mensuels
ret_cac = cac.pct_change(fill_method=None) + 0.03 / 12                       # CAC 40 prix + dividende ~3 %/an (approximation)
ret_msci = ms["msci_gr"].pct_change(fill_method=None)                       # MSCI World dividendes réinvestis (depuis 2001)
ret_msci = ret_msci.fillna(ms["msci_prix"].pct_change(fill_method=None) + 0.02 / 12)
cash_eur = (eu["taux_bce"].shift(1) / 100 / 12).fillna(us.cash)
cash_usd = us.cash

def fwd(ret, n): return (1 + ret).rolling(n).apply(np.prod, raw=True).shift(-n) - 1

# --- indicateurs par zone (+ = favorable) ---
I = pd.DataFrame(index=idx)
# Croissance
I["g_us_cli"], I["g_us_chom"] = us.ind["g_cli"], us.ind["g_chom"]
I["g_ez_cli"] = ((eu["cli_de"] + eu["cli_fr"]) / 2).diff(3).shift(1)
I["g_ez_chom"] = -((eu["chom_fr"].ffill() + eu["chom_de"].ffill()) / 2).diff(6).shift(1)
I["g_cn_cli"] = eu["cli_cn"].diff(3).shift(1)
# Inflation / banques centrales
I["i_us_pce"], I["i_us_taux"] = us.ind["i_pce"], us.ind["i_ff_v2"]
I["i_ez_hicp"] = -(eu["hicp_ga"] - 2).abs().shift(1)
I["i_ez_taux"] = -eu["taux_bce"].diff(6).clip(lower=0)
# Conditions financières
I["f_credit"], I["f_oil"], I["f_usd"] = us.ind["f_credit"], us.ind["f_oil"], us.ind["f_usd"]
I["f_eur_faible"] = -np.log(eu["eurusd"]).diff(6)                            # euro qui baisse = favorable au CAC 40
# Sentiment
I["s_vix"] = us.ind["s_vix"]
I["s_mom_cac"] = cac.shift(1) / cac.shift(12) - 1
I["s_mom_msci"] = ms["msci_prix"].shift(1) / ms["msci_prix"].shift(12) - 1
# Incertitude
I["u_us_epu"] = us.ind["u_epu"]
I["u_ez_epu"] = -eu["epu_eu"]
Z = I.apply(z)

def zone_mix(parts, w):
    """parts = {zone: série de score}, w = {zone: poids} ; renormalise si une zone manque."""
    num = sum(parts[k].fillna(0) * w[k] for k in parts); den = sum(parts[k].notna() * w[k] for k in parts)
    return num / den.replace(0, np.nan)

def piliers(w, dollar_col, mom_col):
    P = pd.DataFrame(index=idx)
    P["croissance"] = zone_mix({"us": Z[["g_us_cli", "g_us_chom"]].mean(axis=1), "ez": Z[["g_ez_cli", "g_ez_chom"]].mean(axis=1),
                                "cn": Z["g_cn_cli"]}, w)
    P["infl"] = zone_mix({"us": Z[["i_us_pce", "i_us_taux"]].mean(axis=1), "ez": Z[["i_ez_hicp", "i_ez_taux"]].mean(axis=1)}, w)
    P["financier"] = Z[["f_credit", "f_oil", dollar_col]].mean(axis=1)
    P["sentiment"] = Z[["s_vix", mom_col]].mean(axis=1)
    P["incertitude"] = zone_mix({"us": Z["u_us_epu"], "ez": Z["u_ez_epu"]}, w)
    return P

W = {"croissance": 25, "infl": 15, "financier": 20, "sentiment": 15, "incertitude": 10}   # valorisation : non disponible
def indice(P):
    num = sum(P[c].fillna(0) * w for c, w in W.items()); den = sum(P[c].notna() * w for c, w in W.items())
    lvl = 50 + 25 * num / den.replace(0, np.nan)
    return lvl, 0.5 * lvl + 0.5 * (50 + 25 * z(lvl.diff(3)))

CFG = {
    "CAC 40": dict(w={"us": .20, "ez": .65, "cn": .15}, dollar="f_eur_faible", mom="s_mom_cac", ret=ret_cac, cash=cash_eur,
                   start="1996-01-01", prix=cac),
    "MSCI World": dict(w={"us": .70, "ez": .20, "cn": .10}, dollar="f_usd", mom="s_mom_msci", ret=ret_msci, cash=cash_usd,
                       start="1998-01-01", prix=ms["msci_prix"]),
}
end, endr = us.end, us.endr

def evaluate(name, s, zone, ret, cash, start):
    f12 = fwd(ret, 12); f3 = fwd(ret, 3)
    d = pd.DataFrame({"s": s, "f12": f12, "f3": f3})[start:end].dropna()
    c = lambda a, b, col: d.loc[a:b, ["s", col]].corr().iloc[0, 1]
    inv = (zone != "prudence").astype(float).shift(1)
    r = (inv * ret + (1 - inv) * cash)[start:endr].dropna(); eq = (1 + r).cumprod()
    rb = ret[start:endr].dropna(); eb = (1 + rb).cumprod()
    return dict(variante=name, corr_12m=c(start, end, "f12"), corr_avant_2008=c(start, "2007-12-01", "f12"),
                corr_2008_2025=c("2008-01-01", end, "f12"), corr_3m=c(start, end, "f3"),
                tcam=eq.iloc[-1] ** (12 / len(r)) - 1, perte_max=(eq / eq.cummax() - 1).min(), investi=inv[start:endr].mean(),
                tcam_bh=eb.iloc[-1] ** (12 / len(rb)) - 1, perte_max_bh=(eb / eb.cummax() - 1).min())

RES, OUT = {}, {}
for nom, c in CFG.items():
    P = piliers(c["w"], c["dollar"], c["mom"])
    lvl, tr = indice(P)
    zc = pd.cut(pct_rank(lvl), [-.01, .2, .8, 1.01], labels=["prudence", "neutre", "favorable"])
    zd = pd.cut(pct_rank(tr), [-.01, .2, .8, 1.01], labels=["prudence", "neutre", "favorable"])
    RES[nom] = pd.DataFrame([evaluate("C. Niveau, seuils percentiles", lvl, zc, c["ret"], c["cash"], c["start"]),
                             evaluate("D. C + tendance du score", tr, zd, c["ret"], c["cash"], c["start"])]).set_index("variante")
    OUT[nom] = dict(P=P, lvl=lvl, D=tr, pct=pct_rank(tr), zone=zd, prix=c["prix"], ret=c["ret"])

if __name__ == "__main__":
    pd.set_option("display.width", 220)
    for nom in CFG:
        print(f"\n=== {nom} ({CFG[nom]['start'][:4]}-2025) ===")
        print(RES[nom].round(3).T.to_string())
        P, tr = OUT[nom]["P"], OUT[nom]["D"]
        f12 = fwd(CFG[nom]["ret"], 12)
        print("corr piliers:", P[CFG[nom]["start"]:end].corrwith(f12[CFG[nom]["start"]:end]).round(2).to_dict())
        last = us.FIN
        print("Dernière:", "D=%.1f pct=%.2f zone=%s" % (tr[last], OUT[nom]["pct"][last], OUT[nom]["zone"][last]), P.loc[last].round(2).to_dict())
