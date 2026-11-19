"""PHYS discount/premium to NAV, reconstructed, and the economics of switching PHYS -> GLDM.
Anchor: Sprott's published figures for 2026-11-18 (NAV $28.83, close $28.02, discount -2.81%, MER 0.39%).
History: PHYS and GLD both hold only bullion and pay nothing out, and GLD trades at its NAV, so the PHYS/GLD
price ratio moves with PHYS's premium/discount (plus the tiny fee difference, corrected below).
Writes discount.json, charts/01_phys_discount.png."""
import json, os, time
import httpx, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "_cache"); os.makedirs(CACHE, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-script"}
ANCHOR = dict(date="2026-11-18", nav=28.83, close=28.02, discount=-0.0281, mer_phys=0.0039, source="sprott.com PHYS page, 'As of November 18, 2026'")
FEES = dict(PHYS=0.0039, GLD=0.0040, GLDM=0.0010, IAUM=0.0009)
POS = dict(shares=1872, as_of="2026-11-18 (IBKR ...3321 positions)")


def raw(sym):
    p = os.path.join(CACHE, f"{sym}.json")
    if not os.path.exists(p):
        r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"period1": 0, "period2": int(pd.Timestamp("2026-11-19", tz="UTC").timestamp()), "interval": "1d"},
                      headers=H, timeout=60); r.raise_for_status(); open(p, "wb").write(r.content)
    res = json.load(open(p))["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=idx).dropna(); return s[~s.index.duplicated(keep="last")]


p, g, m = raw("PHYS"), raw("GLD"), raw("GLDM")
x = pd.concat([p, g], axis=1, keys=["PHYS", "GLD"], sort=True).dropna().loc[:ANCHOR["date"]]
assert abs(x["PHYS"].iloc[-1] - ANCHOR["close"]) < 0.015, x.tail(2)
yrs = (x.index[-1] - x.index).days / 365.25
ratio = x["PHYS"] / x["GLD"]
# NAV_PHYS/NAV_GLD drifts by the fee difference (GLD 0.40% - PHYS 0.39% = +0.01%/yr in PHYS's favour): undo it going back in time
navratio = (ANCHOR["nav"] / x["GLD"].iloc[-1]) * np.exp(-(FEES["GLD"] - FEES["PHYS"]) * yrs)
disc = ratio / navratio - 1
def stat(s):
    return dict(median=float(s.median()), mean=float(s.mean()), p10=float(s.quantile(.1)), p90=float(s.quantile(.9)), min=float(s.min()), max=float(s.max()),
                share_wider_than_now=float((s <= ANCHOR["discount"]).mean()), n=int(len(s)))
out = dict(anchor=ANCHOR, fees=FEES, now=float(disc.iloc[-1]),
           windows={k: stat(disc.loc[a:]) for k, a in (("1y", "2025-11-19"), ("3y", "2023-11-19"), ("5y", "2021-11-19"), ("10y", "2016-11-19"), ("since_2012", "2012-01-01"))},
           by_year={int(y): float(v) for y, v in disc.groupby(disc.index.year).median().items()})
mo = disc.loc["2012":].resample("ME").last(); phi = float(np.corrcoef(mo[:-1], mo[1:])[0, 1]); out["monthly_ar1"] = phi; out["half_life_months"] = float(np.log(.5) / np.log(phi))
price = ANCHOR["close"]; val = POS["shares"] * price; fee_gap = FEES["PHYS"] - FEES["GLDM"]
econ = dict(position_usd=val, shares=POS["shares"], fee_gap=fee_gap, saving_per_year=val * fee_gap, discount_cost_now_vs_nav=-ANCHOR["discount"] * val,
            trading_cost_est=val * 2 * 0.0003, breakeven_years={})
for nm, target in (("stays where it is", ANCHOR["discount"]), ("returns to its 1-year median", out["windows"]["1y"]["median"]), ("returns to its 3-year median", out["windows"]["3y"]["median"]), ("closes to zero", 0.0)):
    forgone = max(target - ANCHOR["discount"], 0) * val
    econ["breakeven_years"][nm] = dict(target_discount=target, forgone_usd=forgone, years=(forgone + econ["trading_cost_est"]) / econ["saving_per_year"])
out["economics"] = econ
# realized check: GLDM vs PHYS vs GLD total return since GLDM's first full day
y = pd.concat([p, g, m], axis=1, keys=["PHYS", "GLD", "GLDM"], sort=True).dropna().loc[:ANCHOR["date"]]; n = (y.index[-1] - y.index[0]).days / 365.25
ann = (y.iloc[-1] / y.iloc[0]) ** (1 / n) - 1
out["realized_since_gldm"] = dict(start=str(y.index[0].date()), years=n, **{k: float(v) for k, v in ann.items()}, phys_discount_at_start=float(disc.loc[y.index[0]]),
                                  gap_from_discount_change=float(((1 + ANCHOR["discount"]) / (1 + disc.loc[y.index[0]])) ** (1 / n) - 1))
json.dump(out, open(os.path.join(HERE, "discount.json"), "w"), indent=1)

INK, INK2, MUT, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": AX, "xtick.color": MUT, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
fig, axs = plt.subplots(2, 1, figsize=(11, 8.4), gridspec_kw={"hspace": .38, "height_ratios": [1.25, 1]})
ax = axs[0]; d = disc.loc["2016":] * 100; ax.plot(d.index, d.values, color="#2a78d6", lw=1.3); ax.axhline(0, color=AX, lw=1.2)
for nm, col, dy in (("3y", "#eb6834", 9), ("1y", "#1baf7a", -15)):
    v = out["windows"][nm]["median"] * 100; a0 = d.index[-1] - pd.DateOffset(years=int(nm[:-1])); ax.plot([a0, d.index[-1]], [v, v], color=col, lw=2.2)
    ax.annotate(f"{nm[:-1]}-year median {v:+.1f}%", (a0, v), xytext=(-6, dy), textcoords="offset points", color=INK2, fontsize=9, ha="right")
ax.plot(d.index[-1], d.iloc[-1], "o", color="#2a78d6", ms=8, mec=SURF, mew=1.5); ax.annotate(f"Nov 18: {d.iloc[-1]:+.1f}%", (d.index[-1], d.iloc[-1]), xytext=(10, -4), textcoords="offset points", ha="left", color=INK, fontweight="bold")
ax.set_xlim(d.index[0], d.index[-1] + pd.Timedelta(days=330))
ax.set_title("PHYS price vs the value of its gold (% premium or discount), 2016-2026", loc="left", color=INK, fontsize=12, fontweight="bold")
ax.set_ylabel("% of net asset value")
ax = axs[1]; yrs_ = np.arange(0, 12.01, .25); save = econ["saving_per_year"] * yrs_
ax.plot(yrs_, save, color="#2a78d6", lw=2.2, label=f"Cumulative fee saving in GLDM (${econ['saving_per_year']:.0f}/yr)")
cols = ["#898781", "#1baf7a", "#eb6834", "#eda100"]
for (nm, b), col in zip(econ["breakeven_years"].items(), cols):
    c0 = b["forgone_usd"] + econ["trading_cost_est"]; ax.axhline(c0, color=col, lw=1.6)
    ax.annotate(f"If the discount {nm}: switching now costs ${c0:,.0f}  (break-even {b['years']:.1f} yrs)", (12, c0), xytext=(0, 4), textcoords="offset points", ha="right", color=INK2, fontsize=8.8)
ax.set_xlim(0, 12); ax.set_ylim(0, max(save.max(), econ["discount_cost_now_vs_nav"]) * 1.12); ax.set_xlabel("Years after switching"); ax.set_ylabel("US$")
ax.legend(loc="upper left", frameon=False, labelcolor=INK2)
ax.set_title(f"Break-even on the ${val:,.0f} position: fee saving vs the discount given up by selling now", loc="left", color=INK, fontsize=12, fontweight="bold")
fig.text(.01, .01, "Discount history reconstructed from the PHYS/GLD price ratio, anchored to Sprott's published NAV for 2026-11-18; the error grows by roughly 0.1-0.2 pt per year going back.\nFees: PHYS 0.39%, GLDM 0.10%.", color=MUT, fontsize=8.3)
fig.savefig(os.path.join(HERE, "charts", "01_phys_discount.png"), dpi=170, bbox_inches="tight")
print(json.dumps({k: v for k, v in out.items() if k != "by_year"}, indent=1)); print({y: round(v * 100, 2) for y, v in out["by_year"].items()})
