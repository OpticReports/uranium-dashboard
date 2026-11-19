"""Extra data for the structure study + stand-in validation gates (PREREG 'Stand-ins and gates').
Reuses the overlay study's fetchers. Writes _cache/panel2.pkl and ../gates.json. No arm is run here."""
import hashlib, io, json, os, pickle, sys, zipfile
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); STUDY = os.path.dirname(HERE)
OV = os.path.join(os.path.dirname(STUDY), "b5_overlay_2026-11", "code"); sys.path.insert(0, OV)
os.environ["B5_CACHE"] = os.path.join(STUDY, "_cache"); os.makedirs(os.environ["B5_CACHE"], exist_ok=True)
import prep as P  # noqa: E402  (overlay fetchers; cache dir redirected above)
OVC = os.path.join(os.path.dirname(STUDY), "b5_overlay_2026-11", "_cache")
END = P.END
NEW = ["BTAL", "DBMF", "AQMIX", "TIP", "USMV", "AVLV", "DFLVX", "UUP", "NTSX", "GDE", "RSST", "GLDM", "CTA"]


def cboe(idx):
    raw = P._cached(f"cboe_{idx}.csv", lambda: P._get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{idx}_History.csv").content)
    df = pd.read_csv(io.BytesIO(raw)); s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0], format="%m/%d/%Y")).dropna()
    return s.loc[s.index <= END]


def french_daily():
    raw = P._cached("ff_daily.zip", lambda: P._get("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip").content)
    t = zipfile.ZipFile(io.BytesIO(raw)); txt = t.read(t.namelist()[0]).decode("latin1").split("\n")
    rows = [l.split(",") for l in txt if l[:8].strip().isdigit() and len(l[:8].strip()) == 8]
    df = pd.DataFrame(rows).iloc[:, :5]; df.columns = ["d", "mkt", "smb", "hml", "rf"]
    df.index = pd.to_datetime(df["d"].str.strip(), format="%Y%m%d"); return df[["mkt", "rf"]].astype(float) / 100


def aqr_bab():
    raw = P._cached("aqr_bab_daily.xlsx", lambda: P._get("https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Betting-Against-Beta-Equity-Factors-Daily.xlsx").content)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True); ws = wb["BAB Factors"]
    hdr = None; out = {}
    for row in ws.iter_rows(values_only=True):
        if hdr is None:
            if row and row[0] == "DATE":
                hdr = list(row); j = hdr.index("USA")
            continue
        if row[0] is None or row[j] is None:
            continue
        out[pd.Timestamp(row[0]) if not isinstance(row[0], str) else pd.to_datetime(row[0], format="%m/%d/%Y")] = float(row[j])
    return pd.Series(out).sort_index()


def corr(a, b, monthly=False):
    x = pd.concat([a, b], axis=1).dropna()
    if monthly:
        x = (1 + x).resample("ME").prod() - 1
    return float(x.corr().iloc[0, 1]), len(x)


def main():
    p = pickle.load(open(os.path.join(OVC, "panel.pkl"), "rb")); cal = p["cal"]; ret = p["ret"].copy(); meta = {}
    for s in NEW:
        df, h = P.yahoo(s); ret[s] = df["adj"].pct_change().reindex(cal); meta[s] = dict(first=str(df.index.min().date()), last=str(df.index.max().date()), hash=h)
    s = cboe("CLLZ"); ret["CLLZ"] = s.pct_change().reindex(cal)        # PPUT stays exactly as in the overlay panel (tape T2 depends on it)
    ff = french_daily(); bab = aqr_bab()
    meta["french_last"] = str(ff.index.max().date()); meta["bab_first"] = str(bab.index.min().date()); meta["bab_last"] = str(bab.index.max().date())
    ret["BAB_US"] = bab.reindex(cal); ret["MKT_EX"] = ff["mkt"].reindex(cal)
    cash = ret["BIL"]
    G = {}
    # ---- BTAL stand-in: a + b*BAB + c*MKT, fitted on real BTAL
    m = ret["BTAL"].notna() & ret["BAB_US"].notna() & ret["MKT_EX"].notna()
    X = np.column_stack([np.ones(m.sum()), ret["BAB_US"][m].values, ret["MKT_EX"][m].values]); y = ret["BTAL"][m].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None); fit = pd.Series(X @ beta, index=ret.index[m])
    cd, n = corr(ret["BTAL"][m], fit); cm, _ = corr(ret["BTAL"][m], fit, True)
    model = beta[0] + beta[1] * ret["BAB_US"] + beta[2] * ret["MKT_EX"]
    G["BTAL"] = dict(a_ann=float(beta[0] * 252), b_bab=float(beta[1]), c_mkt=float(beta[2]), n=n, corr_daily=cd, corr_monthly=cm,
                     passed=bool(cd >= .70 and cm >= .80), fit_from=str(ret.index[m][0].date()), fit_to=str(ret.index[m][-1].date()),
                     ann_real=float((1 + ret["BTAL"][m]).prod() ** (252 / n) - 1), ann_model=float((1 + fit).prod() ** (252 / n) - 1),
                     model_last=str(model.dropna().index.max().date()))
    ret["BTAL_MODEL"] = model
    # ---- DBMF chain
    cdm, n1 = corr(ret["AQMIX"], ret["DBMF"], True); cdd, _ = corr(ret["AQMIX"], ret["DBMF"])
    G["DBMF"] = dict(corr_monthly=cdm, corr_daily=cdd, months=n1, passed=bool(cdm >= .60))
    cav, n2 = corr(ret["DFLVX"], ret["AVLV"], True); G["AVLV"] = dict(corr_monthly=cav, months=n2, passed=bool(cav >= .90))
    # ---- financing gate: stacked funds vs synthetic recipe at T-bills + 0.50%
    def stack(a, b, A, B, fee, spread=.005):
        return a * ret[A] + b * ret[B] - (a + b - 1) * (cash + spread / 252) - fee / 252
    trend = ret["KMLM"]
    for nm, syn, fee in (("GDE", stack(.9, .9, "SPY", "GLD", .0020), .0020), ("RSST", stack(1.0, 1.0, "SPY", "DBMF", .0099), .0099),
                         ("RSST_vs_KMLM_recipe", stack(1.0, 1.0, "SPY", "KMLM", .0099), .0099)):
        real = ret[nm.split("_")[0]]; x = pd.concat([real, syn], axis=1).dropna(); yrs = len(x) / 252
        ar = (1 + x.iloc[:, 0]).prod() ** (1 / yrs) - 1; asyn = (1 + x.iloc[:, 1]).prod() ** (1 / yrs) - 1
        G[f"financing_{nm}"] = dict(years=yrs, ann_real=float(ar), ann_synth=float(asyn), gap=float(ar - asyn), corr_daily=float(x.corr().iloc[0, 1]),
                                    te=float((x.iloc[:, 0] - x.iloc[:, 1]).std() * np.sqrt(252)), passed=bool(abs(ar - asyn) <= .015))
    # ---- G13 gold wrapper arithmetic
    x = pd.concat([ret["PHYS"], ret["GLDM"], ret["GLD"]], axis=1).dropna(); yrs = len(x) / 252
    ann = ((1 + x).prod() ** (1 / yrs) - 1)
    G["gold_wrapper"] = dict(years=yrs, phys=float(ann["PHYS"]), gldm=float(ann["GLDM"]), gld=float(ann["GLD"]), gldm_minus_phys=float(ann["GLDM"] - ann["PHYS"]),
                             vol_phys=float(x["PHYS"].std() * np.sqrt(252)), vol_gldm=float(x["GLDM"].std() * np.sqrt(252)), corr=float(x[["PHYS", "GLDM"]].corr().iloc[0, 1]))
    G["meta"] = meta
    json.dump(G, open(os.path.join(STUDY, "gates.json"), "w"), indent=1)
    p2 = dict(p); p2["ret"] = ret; pickle.dump(p2, open(os.path.join(STUDY, "_cache", "panel2.pkl"), "wb"))
    print(json.dumps({k: v for k, v in G.items() if k != "meta"}, indent=1)); print(meta)


if __name__ == "__main__":
    main()
