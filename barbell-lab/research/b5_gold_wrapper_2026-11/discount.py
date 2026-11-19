"""PHYS premium/discount to NAV and the economics of switching PHYS -> GLDM.

Source for PHYS: the daily series Sprott embeds in its own page (market price, NAV, premium/discount, 2010-02-25 on):
https://sprott.com/investment-strategies/physical-bullion-trusts/gold/net-asset-value-premium-discount/
GLDM / GLD closes: Yahoo v8 chart (unadjusted; neither fund pays distributions).
(A first draft reconstructed the discount from the PHYS/GLD price ratio; the independent check showed that was
wrong by up to 2 pts in older years. It is not used anywhere below.)
Writes sprott_phys_series.csv, discount.json, charts/01_phys_discount.png.  Refresh the page: B5_REFRESH=1."""
import json, os, re
import httpx, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "_cache"); os.makedirs(CACHE, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
URL = "https://sprott.com/investment-strategies/physical-bullion-trusts/gold/net-asset-value-premium-discount/"
FEES = dict(PHYS=0.0039, GLDM=0.0010, IAUM=0.0009, GLD=0.0040)
SOURCES = dict(PHYS_fee_nav_discount=URL, GLDM="https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-minishares-trust-gldm (expense ratio 0.10%, net assets $28.8B, "
               "30-day median bid/ask spread 0.01%, custodian JPMorgan; read 2026-11-19)", IAUM="https://stockanalysis.com/etf/iaum/ (0.09%, $7.8B)")
SHARES = 1872; AVG_COST = 33.3158                      # IBKR ...3321 positions, read 2026-11-18
COST_BPS = dict(PHYS=8, GLDM=2)                        # one-way, barbell-lab/config/backtest.yaml convention (GLDM from its quoted spread)


def page():
    p = os.path.join(CACHE, "sprott_phys_page.html")
    if not os.path.exists(p) or os.environ.get("B5_REFRESH"):
        r = httpx.get(URL, headers=H, timeout=60, follow_redirects=True); r.raise_for_status(); open(p, "w").write(r.text)
    return open(p).read()


def series(t, name):
    i = t.index(f"name: '{name}'"); j = t.index("data: [[", i); k = t.index("]]", j)
    pts = re.findall(r"Date\.UTC\((\d+),(\d+),(\d+)\),(-?[\d.]+)", t[j:k + 2])
    return pd.Series({pd.Timestamp(int(y), int(m) + 1, int(d)): float(v) for y, m, d, v in pts}).sort_index()


def yahoo(sym):
    p = os.path.join(CACHE, f"{sym}.json")
    if not os.path.exists(p):
        r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"period1": 0, "period2": int(pd.Timestamp("2026-11-19", tz="UTC").timestamp()), "interval": "1d"},
                      headers=H, timeout=60); r.raise_for_status(); open(p, "wb").write(r.content)
    res = json.load(open(p))["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=idx).dropna(); return s[~s.index.duplicated(keep="last")]


t = page()
S = pd.DataFrame({"price": series(t, "Share Price"), "nav": series(t, "Net Asset Value"), "disc": series(t, "Premium/Discount to Net Asset Value")}).dropna()
S.to_csv(os.path.join(HERE, "sprott_phys_series.csv"), float_format="%.4f")
asof = S.index[-1]; d = S["disc"]; now = float(d.iloc[-1]); price = float(S["price"].iloc[-1]); nav = float(S["nav"].iloc[-1])
assert abs((price / nav - 1) * 100 - now) < 0.06, (price, nav, now)          # the three published series agree
perf = {n: dict(re.findall(r"\['([^']+)',\s*(-?[\d.]+)\]", t[t.index(f"name: '{n}'"):t.index("]", t.index("] }", t.index(f"name: '{n}'")))]))
        for n in ("PHYS (NAV)", "PHYS (Market Price)", "Benchmark: Spot Gold Price")}
perf = {k: {a: float(b) for a, b in v.items()} for k, v in perf.items()}


def stat(s):
    return dict(median=float(s.median()), min=float(s.min()), max=float(s.max()), share_wider_than_now=float((s < now).mean()), days_wider=int((s < now).sum()), n=int(len(s)))


out = dict(as_of=str(asof.date()), price=price, nav=nav, discount=now, fees=FEES, sources=SOURCES, n_days=int(len(S)), first=str(S.index[0].date()),
           windows={k: stat(d.loc[asof - pd.DateOffset(years=y) + pd.Timedelta(days=1):]) for k, y in (("1y", 1), ("3y", 3), ("5y", 5))},
           by_year={int(y): float(v) for y, v in d.loc["2019":].groupby(d.loc["2019":].index.year).median().items()},
           daily_change_sd=float(d.loc[asof - pd.DateOffset(years=1):].diff().std()), sprott_annualised_returns=perf)
# episodes: first close at -2.7% or wider after being narrower; trading days until a close at -2.4% or narrower
ep = []; i = 0; v = d.values; idx = d.index
while i < len(v):
    if v[i] <= -2.7 and (i == 0 or v[i - 1] > -2.7):
        j = i
        while j < len(v) and v[j] < -2.4:
            j += 1
        ep.append(dict(start=str(idx[i].date()), days=(j - i) if j < len(v) else None)); i = j
    i += 1
done = [e["days"] for e in ep if e["days"] is not None]
out["episodes_wider_than_2p7"] = dict(n=len(ep), closed=len(done), median_days=float(np.median(done)), max_days=int(max(done)), open_now=[e for e in ep if e["days"] is None],
                                      in_2026_closed=sum(e["start"].startswith("2026") for e in ep if e["days"] is not None),
                                      lasting_2_days_or_less=sum(1 for x in done if x <= 2))
# NAV-level lag: PHYS NAV vs GLDM (which trades within a few bps of its NAV) over the same dates
g = yahoo("GLDM"); gl = yahoo("GLD"); lag = {}
for k, a in (("since GLDM launch", "2018-06-26"), ("5y", str((asof - pd.DateOffset(years=5)).date())), ("3y", str((asof - pd.DateOffset(years=3)).date())), ("1y", str((asof - pd.DateOffset(years=1)).date()))):
    x = pd.concat([S["nav"], S["price"], g, gl], axis=1, keys=["phys_nav", "phys_price", "gldm", "gld"], sort=True).dropna().loc[a:asof]
    n = (x.index[-1] - x.index[0]).days / 365.25; ann = (x.iloc[-1] / x.iloc[0]) ** (1 / n) - 1
    lag[k] = dict(start=str(x.index[0].date()), years=n, **{c: float(ann[c]) for c in x}, nav_gap=float(ann["gldm"] - ann["phys_nav"]), price_gap=float(ann["gldm"] - ann["phys_price"]),
                  discount_start=float(d.reindex(x.index).iloc[0]), discount_end=now)
out["nav_level_lag"] = lag
gm = pd.concat([d.diff(), gl.pct_change()], axis=1, keys=["dd", "gold"], sort=True).dropna().loc[asof - pd.DateOffset(years=3):]
out["discount_change_on_big_gold_days_3y"] = dict(falls_over_2pct=dict(n=int((gm.gold < -.02).sum()), mean_change=float(gm.dd[gm.gold < -.02].mean())),
                                                 rises_over_2pct=dict(n=int((gm.gold > .02).sum()), mean_change=float(gm.dd[gm.gold > .02].mean())))
y1 = pd.concat([S["price"].pct_change(), g.pct_change()], axis=1, sort=True).dropna(); out["corr_daily_price_phys_gldm"] = dict(since_2018=float(y1.corr().iloc[0, 1]), last_year=float(y1.loc[asof - pd.DateOffset(years=1):].corr().iloc[0, 1]))

val = SHARES * price; navval = SHARES * nav; trade = val * (COST_BPS["PHYS"] + COST_BPS["GLDM"]) / 1e4
save_fee = val * (FEES["PHYS"] - FEES["GLDM"])                              # one basis (market value), i.e. at a constant discount
gap_hist = float(np.median([lag[k]["nav_gap"] for k in lag])); save_hist = val * gap_hist
econ = dict(shares=SHARES, market_value=val, nav_value=navval, discount_usd=navval - val, usd_per_point_of_discount=navval / 100, trading_cost=trade,
            unrealised_pnl=SHARES * (price - AVG_COST), ounces=SHARES * 3804356 / 492711798,                    # trust ounces / units outstanding, Sprott page
            saving_fee_only=save_fee, hist_nav_gap=gap_hist, saving_hist_gap=save_hist, gldm_shares_at_asof=val / float(g.loc[:asof].iloc[-1]), scenarios={})
for nm, target in (("stays where it is", now), ("returns to its 1-year median", out["windows"]["1y"]["median"]), ("returns to its 3-year median", out["windows"]["3y"]["median"]), ("closes to zero", 0.0)):
    forgone = max(target - now, 0) / 100 * navval
    econ["scenarios"][nm] = dict(target=target, forgone_usd=forgone, breakeven_years_fee_only=(forgone + trade) / save_fee, breakeven_years_hist_gap=(forgone + trade) / save_hist)
out["economics"] = econ
json.dump(out, open(os.path.join(HERE, "discount.json"), "w"), indent=1)

INK, INK2, MUT, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": AX, "xtick.color": MUT, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
fig, axs = plt.subplots(2, 1, figsize=(11, 8.6), gridspec_kw={"hspace": .38, "height_ratios": [1.2, 1]})
ax = axs[0]; dd = d.loc["2016":]; ax.plot(dd.index, dd.values, color="#2a78d6", lw=1.1); ax.axhline(0, color=AX, lw=1.2)
for nm, col, dy in (("3y", "#eb6834", 44), ("1y", "#1baf7a", -30)):
    v_ = out["windows"][nm]["median"]; a0 = asof - pd.DateOffset(years=int(nm[:-1])); ax.plot([a0, asof], [v_, v_], color=col, lw=2.4)
    ax.annotate(f"{nm[:-1]}-year median {v_:+.2f}%", (a0, v_), xytext=(-6, dy), textcoords="offset points", color=INK2, fontsize=9, ha="right")
ax.plot(asof, now, "o", color="#2a78d6", ms=8, mec=SURF, mew=1.5); ax.annotate(f"{asof:%b %d}: {now:+.2f}%", (asof, now), xytext=(10, -4), textcoords="offset points", color=INK, fontweight="bold")
ax.set_xlim(dd.index[0], asof + pd.Timedelta(days=360)); ax.set_ylabel("% of net asset value")
ax.set_title("PHYS market price vs the value of its gold (premium or discount to NAV), Sprott's published daily series", loc="left", color=INK, fontsize=12, fontweight="bold")
ax = axs[1]; yrs = np.arange(0, 12.01, .25)
ax.plot(yrs, save_fee * yrs, color="#2a78d6", lw=2.2, label=f"Fee difference only (${save_fee:.0f}/yr)")
ax.plot(yrs, save_hist * yrs, color="#2a78d6", lw=2.2, ls=(0, (5, 3)), label=f"If PHYS's NAV keeps lagging GLDM as it has ({gap_hist * 100:.2f} pt/yr: ${save_hist:.0f}/yr)")
for (nm, b), col in zip(econ["scenarios"].items(), ["#898781", "#1baf7a", "#eb6834", "#eda100"]):
    c0 = b["forgone_usd"] + trade; ax.axhline(c0, color=col, lw=1.6)
    ax.annotate(f"If the discount {nm}: switching now costs ${c0:,.0f}", (12, c0), xytext=(0, 4), textcoords="offset points", ha="right", color=INK2, fontsize=8.8)
ax.set_xlim(0, 12); ax.set_ylim(0, 2100); ax.set_xlabel("Years after switching"); ax.set_ylabel("US$"); ax.legend(loc="upper left", frameon=False, labelcolor=INK2, title="Cumulative saving in GLDM", title_fontsize=9)
ax.set_title(f"Break-even on the ${val:,.0f} position: saving vs the discount given up by selling now", loc="left", color=INK, fontsize=12, fontweight="bold")
fig.text(.01, .01, f"PHYS data: Sprott, as of {asof:%Y-%m-%d}. Fees: PHYS 0.39%, GLDM 0.10%. Trading cost assumed: 8 bps to sell PHYS, 2 bps to buy GLDM.", color=MUT, fontsize=8.3)
fig.savefig(os.path.join(HERE, "charts", "01_phys_discount.png"), dpi=170, bbox_inches="tight")
print(json.dumps({k: v for k, v in out.items() if k not in ("sources",)}, indent=1))
