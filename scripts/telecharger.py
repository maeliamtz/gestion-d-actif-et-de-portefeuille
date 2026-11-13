"""Télécharge toutes les sources de l'appli GAP et écrit les fichiers CSV utilisés par le calcul.

Sources : FRED (St. Louis Fed), Yahoo Finance (CAC 40), MSCI (MSCI World), multpl.com (bénéfices S&P 500),
github.com/datasets (S&P 500 Shiller, VIX, Brent, taux 10 ans US).
Si une source ne répond pas, le fichier précédent (déjà dans le dépôt) est conservé.
"""
import io, os, sys, json, re, time, datetime as dt
import numpy as np, pandas as pd, requests

D = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(D, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (appli-gap; mise a jour mensuelle)"}
FIN = (pd.Timestamp.today().to_period("M") - 1).to_timestamp()        # dernier mois complet
MOIS = pd.date_range("1984-01-01", FIN, freq="MS")
erreurs = []

def get(url, **kw):
    for essai in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60, **kw); r.raise_for_status(); return r
        except Exception as e:
            if essai == 2: raise
            time.sleep(5)

def fred(id_, debut="1983-01-01"):
    r = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}&cosd={debut}&fq=Monthly&fam=avg")
    s = pd.read_csv(io.StringIO(r.text))
    s.columns = ["date", "v"]
    s["v"] = pd.to_numeric(s["v"], errors="coerce")
    s = s.dropna(); s.index = pd.to_datetime(s["date"]).dt.to_period("M").dt.to_timestamp()
    return s["v"]

def ecrire(nom, df):
    df.to_csv(os.path.join(D, nom), index=False); print(f"  {nom}: {len(df)} lignes, dernier mois {df.iloc[-1, 0]}")

def etape(nom, fn):
    print(nom)
    try: fn()
    except Exception as e:
        erreurs.append(f"{nom}: {e}"); print(f"  ÉCHEC ({e}) : fichier précédent conservé")

def mois_str(i): return [d.strftime("%Y-%m") for d in i]
def f(s, d): return s.round(d)

# ---------- FRED US ----------
def fred_us():
    S = {k: fred(k) for k in ["BAA10Y", "UNRATE", "FEDFUNDS", "PCEPILFE", "DTWEXBGS", "TWEXBMTH", "USEPUINDXM",
                              "USALOLITOAASTSAM", "TB3MS", "BAMLH0A0HYM2"]}
    S = {k: v.reindex(MOIS) for k, v in S.items()}
    r = S["DTWEXBGS"]["2006-01-01"] / S["TWEXBMTH"]["2006-01-01"]
    dollar = S["DTWEXBGS"].where(S["DTWEXBGS"].index >= "2006-01-01", S["TWEXBMTH"] * r)
    pce = (S["PCEPILFE"] / S["PCEPILFE"].shift(12) - 1) * 100
    ecrire("fred_us.csv", pd.DataFrame({"mois": mois_str(MOIS), "baa10y": f(S["BAA10Y"], 2), "chomage": f(S["UNRATE"], 1),
        "fedfunds": f(S["FEDFUNDS"], 2), "pce_core_ga": f(pce, 2), "dollar": f(dollar, 1), "epu": f(S["USEPUINDXM"], 0),
        "cli": f(S["USALOLITOAASTSAM"], 2), "tbill3m": f(S["TB3MS"], 2), "hy": f(S["BAMLH0A0HYM2"], 2)}))

# ---------- FRED zone euro / Chine ----------
def fred_eu():
    ids = ["DEULOLITOAASTSAM", "FRALOLITOAASTSAM", "CHNLOLITOAASTSAM", "LRHUTTTTFRM156S", "LRHUTTTTDEM156S",
           "CP0000EZ19M086NEST", "ECBDFR", "IRSTCI01EZM156N", "IRLTLT01DEM156N", "DEXUSEU", "CCUSMA02EZM618N", "EUEPUINDXM"]
    S = {k: fred(k).reindex(MOIS) for k in ids}
    hicp = (S["CP0000EZ19M086NEST"] / S["CP0000EZ19M086NEST"].shift(12) - 1) * 100
    bce = S["ECBDFR"].fillna(S["IRSTCI01EZM156N"])
    eur = S["DEXUSEU"].fillna(1 / S["CCUSMA02EZM618N"])
    ecrire("fred_eu_cn.csv", pd.DataFrame({"mois": mois_str(MOIS), "cli_de": f(S["DEULOLITOAASTSAM"], 2),
        "cli_fr": f(S["FRALOLITOAASTSAM"], 2), "cli_cn": f(S["CHNLOLITOAASTSAM"], 2), "chom_fr": f(S["LRHUTTTTFRM156S"], 1),
        "chom_de": f(S["LRHUTTTTDEM156S"], 1), "hicp_ga": f(hicp, 2), "taux_bce": f(bce, 2), "bund10": f(S["IRLTLT01DEM156N"], 2),
        "eurusd": f(eur, 3), "epu_eu": f(S["EUEPUINDXM"], 0)}))

# ---------- CAC 40 (Yahoo Finance) ----------
def cac40():
    j = get("https://query1.finance.yahoo.com/v8/finance/chart/%5EFCHI?interval=1mo&range=max").json()["chart"]["result"][0]
    ts = pd.to_datetime(np.array(j["timestamp"]) + 3 * 86400, unit="s")
    s = pd.Series(j["indicators"]["quote"][0]["close"], index=ts.to_period("M").to_timestamp()).dropna().round(0)
    s = s[~s.index.duplicated(keep="last")]; s = s[s.index <= FIN]
    ecrire("cac40.csv", pd.DataFrame({"mois": mois_str(s.index), "cac40": s.astype(int).values}))

# ---------- MSCI World ----------
def msci():
    def niveaux(variant):
        u = ("https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph?currency_symbol=USD"
             f"&index_variant={variant}&start_date=19970101&end_date={dt.date.today():%Y%m%d}&data_frequency=END_OF_MONTH&index_codes=990100")
        L = get(u).json()["indexes"]["INDEX_LEVELS"]
        return pd.Series({pd.Timestamp(str(x["calc_date"])[:6] + "01"): x["level_eod"] for x in L})
    p, g = niveaux("STRD"), niveaux("GRTR")
    df = pd.DataFrame({"p": p, "g": g}).sort_index(); df = df[df.index <= FIN]
    ecrire("msci_world.csv", pd.DataFrame({"mois": mois_str(df.index), "msci_prix": df["p"].round(1).values, "msci_gr": df["g"].round(1).values}))

# ---------- multpl : bénéfices et rendement du dividende du S&P 500 ----------
def multpl():
    def table(url):
        t = get(url).text
        rows = re.findall(r"<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>(.*?)</td>", t, re.S)
        out = {}
        for d, v in rows:
            v = re.sub(r"<[^>]+>|&#x2002;|†|%", "", v).strip()
            try: out[pd.Timestamp(pd.to_datetime(d.strip()).strftime("%Y-%m-01"))] = float(v.replace(",", ""))
            except Exception: pass
        return pd.Series(out).sort_index()
    e = table("https://www.multpl.com/s-p-500-earnings/table/by-month")
    y = table("https://www.multpl.com/s-p-500-dividend-yield/table/by-month")
    df = pd.DataFrame({"e": e, "y": y}).loc["2022-10-01":FIN]
    ecrire("multpl.csv", pd.DataFrame({"mois": mois_str(df.index), "earnings_ttm": df["e"].round(2).values, "div_yield": df["y"].round(2).values}))

# ---------- github.com/datasets ----------
def datasets():
    B = "https://raw.githubusercontent.com/datasets"
    for nom, chemin in [("s-and-p-500.csv", "s-and-p-500/main/data/data.csv"), ("finance-vix.csv", "finance-vix/main/data/vix-daily.csv"),
                        ("oil-prices.csv", "oil-prices/main/data/brent-monthly.csv"), ("bond-yields-us-10y.csv", "bond-yields-us-10y/main/data/monthly.csv")]:
        t = get(f"{B}/{chemin}").text
        open(os.path.join(D, nom), "w").write(t); print(f"  {nom}: {t.count(chr(10))} lignes")

for nom, fn in [("FRED US", fred_us), ("FRED zone euro / Chine", fred_eu), ("CAC 40", cac40), ("MSCI World", msci),
                ("multpl", multpl), ("GitHub datasets", datasets)]:
    etape(nom, fn)

json.dump({"date": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "erreurs": erreurs}, open(os.path.join(D, "maj.json"), "w"), ensure_ascii=False)
print("Erreurs :", erreurs or "aucune")
