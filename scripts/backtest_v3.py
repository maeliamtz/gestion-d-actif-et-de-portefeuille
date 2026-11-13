"""Backtest v3 de l'indice GAP sur le S&P 500 : vraies sources (FRED, multpl, Shiller, CBOE, EIA)."""
import numpy as np, pandas as pd, sys, os
import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
pd.set_option("display.width", 220)

def ms(s):
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp(); return s.groupby(level=0).last()

_sp = pd.read_csv(f"{D}/s-and-p-500.csv", parse_dates=["Date"])
FIN = _sp.loc[_sp["SP500"] > 0, "Date"].max().to_period("M").to_timestamp()      # dernier mois avec un cours du S&P 500
idx = pd.date_range("1984-01-01", FIN, freq="MS")
# --- S&P 500 (Shiller jusqu'à 06/2023, prolongé par multpl) ---
sp = pd.read_csv(f"{D}/s-and-p-500.csv", parse_dates=["Date"]).set_index("Date")
price = ms(sp["SP500"]).reindex(idx)
earn = ms(sp["Earnings"].replace(0, np.nan)).reindex(idx)
div = ms(sp["Dividend"].replace(0, np.nan)).reindex(idx)
mp = pd.read_csv(f"{D}/multpl.csv").set_index("mois"); mp.index = pd.to_datetime(mp.index + "-01")
k = earn["2023-06-01"] / mp.loc["2023-06-01", "earnings_ttm"]           # raccord des deux sources
earn = earn.fillna(mp["earnings_ttm"].reindex(idx) * k)
dy = (div / price)
dy = dy.fillna(mp["div_yield"].reindex(idx) / 100).ffill()
# --- FRED ---
f = pd.read_csv(f"{D}/fred_us.csv").set_index("mois"); f.index = pd.to_datetime(f.index + "-01"); f = f.reindex(idx)
vix = ms(pd.read_csv(f"{D}/finance-vix.csv", parse_dates=["DATE"]).set_index("DATE")["CLOSE"].resample("ME").mean()).reindex(idx)
brent = ms(pd.read_csv(f"{D}/oil-prices.csv", parse_dates=["Date"]).set_index("Date")["Price"]).reindex(idx)
y10 = ms(pd.read_csv(f"{D}/bond-yields-us-10y.csv", parse_dates=["Date"]).set_index("Date")["Rate"]).reindex(idx)

ret = price.pct_change() + dy / 12
fwd12 = (1 + ret).rolling(12).apply(np.prod, raw=True).shift(-12) - 1
fwd3 = (1 + ret).rolling(3).apply(np.prod, raw=True).shift(-3) - 1
cash = f["tbill3m"].shift(1) / 100 / 12

# --- indicateurs (signe + = favorable ; décalage = délai de publication) ---
L = lambda s, n: s.shift(n)
ind = pd.DataFrame(index=idx)
ind["g_cli"] = L(f["cli"].diff(3), 1)
ind["g_chom"] = -L(f["chomage"].ffill().diff(6), 1)
ind["i_pce"] = -L((f["pce_core_ga"] - 2).abs(), 1)
ind["i_ff_v1"] = -L(f["fedfunds"].diff(6), 0)                          # v1 : baisse des taux = favorable
ind["i_ff_v2"] = -L(f["fedfunds"].diff(6).clip(lower=0), 0)             # v2 : seule une hausse pénalise
ind["f_credit"] = -L(f["baa10y"], 0)
ind["f_usd"] = -L(np.log(f["dollar"]).diff(6), 0)
ind["f_oil"] = -L(np.log(brent).diff(6), 0)
ind["v_erp"] = L(earn / price * 100 - y10, 3)
ind["s_vix"] = -vix
ind["s_mom"] = price.shift(1) / price.shift(12) - 1
ind["u_epu"] = -L(f["epu"], 0)

def z(s, win=120, minp=60):
    m = s.rolling(win, min_periods=minp).mean(); sd = s.rolling(win, min_periods=minp).std()
    return ((s - m) / sd).clip(-2, 2)
Z = ind.apply(z)
P = pd.DataFrame(index=idx)
P["croissance"] = Z[["g_cli", "g_chom"]].mean(axis=1)
P["infl_v1"] = Z[["i_pce", "i_ff_v1"]].mean(axis=1)
P["infl_v2"] = Z[["i_pce", "i_ff_v2"]].mean(axis=1)
P["financier"] = Z[["f_credit", "f_usd", "f_oil"]].mean(axis=1)
P["valo"] = Z["v_erp"]
P["sentiment"] = Z[["s_vix", "s_mom"]].mean(axis=1)
P["incertitude"] = Z["u_epu"]

def wavg(W):
    num = sum(P[c].fillna(0) * w for c, w in W.items()); den = sum(P[c].notna() * w for c, w in W.items())
    return 50 + 25 * num / den.replace(0, np.nan)
W1 = {"croissance": 25, "infl_v1": 15, "financier": 20, "valo": 15, "sentiment": 15, "incertitude": 10}
W2 = {"croissance": 25, "infl_v2": 15, "financier": 20, "sentiment": 15, "incertitude": 10}
idx_v1 = wavg(W1)
idx_v2b = wavg(W2)
trend = z(idx_v2b.diff(3))
idx_v2c = 0.5 * idx_v2b + 0.5 * (50 + 25 * trend)

def pct_rank(s, win=120, minp=60):
    return s.rolling(win, min_periods=minp).apply(lambda a: (a[:-1] < a[-1]).mean() if np.isfinite(a[-1]) else np.nan, raw=True)

start = "1991-01-01"
endr = FIN.strftime("%Y-%m-%d")
end = (FIN - pd.DateOffset(months=12)).strftime("%Y-%m-%d")
def zones_abs(s): return pd.cut(s, [-1, 35, 65, 101], labels=["prudence", "neutre", "favorable"])
def zones_pct(s, lo=.2, hi=.8): return pd.cut(pct_rank(s), [-.01, lo, hi, 1.01], labels=["prudence", "neutre", "favorable"])

def strat(zone):
    inv = (zone != "prudence").astype(float).shift(1)
    r = (inv * ret + (1 - inv) * cash)[start:endr].dropna(); eq = (1 + r).cumprod()
    return eq.iloc[-1] ** (12 / len(r)) - 1, (eq / eq.cummax() - 1).min(), inv[start:endr].mean()

def report(name, s, zone):
    d = pd.DataFrame({"s": s, "f12": fwd12, "f3": fwd3, "zone": zone})[start:end].dropna(subset=["s"])
    c = lambda a, b, col: d.loc[a:b, ["s", col]].dropna().corr().iloc[0, 1]
    cagr, dd, inv = strat(zone)
    zs = d.groupby("zone", observed=False)["f12"].agg(["mean", "count"]); zs["part"] = zs["count"] / zs["count"].sum()
    return dict(variante=name, c12=c(start, end, "f12"), c12_9107=c("1991", "2007", "f12"), c12_0825=c("2008", end, "f12"),
                c3=c(start, end, "f3"), tcam=cagr, perte_max=dd, investi=inv,
                **{f"{q}_f12": zs.loc[q, "mean"] for q in zs.index}, **{f"{q}_part": zs.loc[q, "part"] for q in zs.index})

rows = [report("A. Méthode v1 (seuils 35/65)", idx_v1, zones_abs(idx_v1)),
        report("B. v1 + seuils percentiles 20/80", idx_v1, zones_pct(idx_v1)),
        report("C. B + pilier 2 revu + valo hors score", idx_v2b, zones_pct(idx_v2b)),
        report("D. C + tendance du score (3 mois)", idx_v2c, zones_pct(idx_v2c))]
r = ret[start:endr].dropna(); eq = (1 + r).cumprod()
rows.append(dict(variante="Achat-conservation", tcam=eq.iloc[-1] ** (12 / len(r)) - 1, perte_max=(eq / eq.cummax() - 1).min(), investi=1.0))
res = pd.DataFrame(rows).set_index("variante")

if __name__ == "__main__":
    print(res.round(3).T.to_string())
    print("\nCorrélation avec le rendement à 12 mois (1991-2025):")
    allp = pd.concat([P, Z, trend.rename("tendance_score")], axis=1)[start:end]
    print(allp.corrwith(fwd12[start:end]).round(2).to_string())
    print("\nRobustesse D:")
    for h in [1, 3, 6]:
        for lo, hi in [(.15, .85), (.2, .8), (.25, .75)]:
            s = 0.5 * idx_v2b + 0.5 * (50 + 25 * z(idx_v2b.diff(h)))
            cagr, dd, inv = strat(zones_pct(s, lo, hi))
            print(f"  h={h} {lo}/{hi}: c12={s[start:end].corr(fwd12[start:end]):.2f} TCAM={cagr:.3f} DD={dd:.3f} investi={inv:.2f}")
    for dt in ["2000-03-01", "2007-10-01", "2008-10-01", "2009-03-01", "2020-03-01", "2022-06-01"]:
        print(dt, "v1=%.1f  D=%.1f pct=%.2f f12=%.2f" % (idx_v1[dt], idx_v2c[dt], pct_rank(idx_v2c)[dt], fwd12[dt]))
    last = idx_v2c.last_valid_index()
    print("Dernière:", last.date(), "D=%.1f pct=%.2f v1=%.1f" % (idx_v2c[last], pct_rank(idx_v2c)[last], idx_v1[last]))
    print(P.loc[last].round(2).to_dict())
