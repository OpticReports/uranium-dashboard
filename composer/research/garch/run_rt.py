import numpy as np, json, sys, time
sys.path.insert(0, "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/garch")
import garchlib as G
SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
r = np.load(f"{SC}/spy_r.npy"); d = json.load(open(f"{SC}/spy_d.json"))

START = next(i for i, x in enumerate(d) if x >= "2010-01-01")
FITWIN, REFIT = 2500, 21          # rolling 10y fit, monthly refit (desk-realistic)
out = np.full(len(r), np.nan)
params = None; h_prev = None; mu = 0.0; e_prev = 0.0
t0 = time.time()
for t in range(START, len(r)):
    if params is None or (t - START) % REFIT == 0:
        lo = max(0, t - FITWIN)
        hist = r[lo:t]                      # data strictly before t
        params = G.fit(hist)
        mu = hist.mean()
        h_prev = G.filter_h(params, hist)[-1]
        e_prev = r[t-1] - mu
    omega, alpha, beta = params
    h_t = omega + alpha * e_prev**2 + beta * h_prev
    out[t] = np.sqrt(h_t * 252)
    h_prev, e_prev = h_t, r[t] - mu
np.save(f"{SC}/garch/spy_sigma_rt.npy", out)
print(f"done in {time.time()-t0:.0f}s; valid {d[START]}..{d[-1]}", flush=True)
