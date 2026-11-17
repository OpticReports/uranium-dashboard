"""Vectorized B.5 rebalance-delay engine (PREREG sec 1). Paths x k-grid in parallel.
Trigger at close t (known at t's close); fill (full rebalance to target) at close t+k.
Order each day t: drift -> due pending fill executes -> trigger check if nothing pending (k=0 fills now)."""
import numpy as np
BAND = 0.20
KS = np.arange(11)

def run(R, ME, w, c, fam, ks=KS, cancel=False, record=False):
    """R: [P,T,N] (or [T,N]) simple daily returns, row 0 = start close (ignored); ME: [P,T] (or [T]) month-end flags.
    w: [N] target; c: [N] one-way cost fraction per sleeve. fam in {'D','M','MB'}.
    Returns dict with logV [P,K] and (if record, P must be 1) daily values, fills, traded, cost, events."""
    if R.ndim == 2: R = R[None]
    if ME.ndim == 1: ME = ME[None]
    P, T, N = R.shape; K = len(ks)
    w = np.asarray(w, float); c = np.asarray(c, float)
    h = np.broadcast_to(w, (P, K, N)).copy()
    pend = np.full((P, K), -1, np.int32)
    kk = np.broadcast_to(np.asarray(ks, np.int32), (P, K))
    nfill = np.zeros((P, K)); traded = np.zeros((P, K)); costs = np.zeros((P, K))
    if record:
        Vpath = np.ones((K, T)); Hk1 = np.zeros((T, N)); trig_log = [[] for _ in range(K)]
        i1 = list(ks).index(1) if 1 in list(ks) else None
    def execute(mask):
        hm = h[mask]; Vm = hm.sum(-1)
        tr = np.abs(w * Vm[:, None] - hm)
        cost = (tr * c).sum(-1)
        h[mask] = w * (Vm - cost)[:, None]
        nfill[mask] += 1; traded[mask] += tr.sum(-1) / Vm; costs[mask] += cost / Vm
    for t in range(1, T):
        h *= (1.0 + R[:, t, None, :])
        np.subtract(pend, 1, out=pend, where=pend > 0)
        due = pend == 0
        if due.any():
            if cancel and fam != 'M':
                V = h.sum(-1); dev = h / V[..., None] / w - 1
                br = (np.abs(dev) > BAND).any(-1)
                ex = due & br
            else:
                ex = due
            if ex.any(): execute(ex)
            pend[due] = -1
        V = h.sum(-1)
        if fam == 'M':
            trig = (pend < 0) & ME[:, t, None]
            dev = None
        else:
            dev = h / V[..., None] / w - 1
            br = (np.abs(dev) > BAND).any(-1)
            trig = (pend < 0) & br
            if fam == 'MB': trig &= ME[:, t, None]
        if trig.any():
            if record:
                d = h[0] / V[0][:, None] / w - 1
                for j in np.nonzero(trig[0])[0]: trig_log[j].append((t, d[j].copy()))
            now = trig & (kk == 0)
            if now.any(): execute(now)
            later = trig & (kk > 0)
            pend[later] = kk[later]
        if record:
            Vpath[:, t] = h[0].sum(-1)
            if i1 is not None: Hk1[t] = h[0, i1]
    out = dict(logV=np.log(h.sum(-1)), nfill=nfill, traded=traded, costs=costs)
    if record:
        Hk1[0] = w
        out.update(Vpath=Vpath, Hk1=Hk1, trig=trig_log)
    return out

def event_paths(R, H, ts, w, c, ks=KS, horizon=11):
    """Per-event log return over (t, t+horizon] starting from holdings H[t] (normalized), fill at t+k (k=0: at t).
    Returns [E, K] log values. Events with t+horizon beyond data must be filtered by caller."""
    ts = np.asarray(ts); E = len(ts); K = len(ks)
    h0 = H[ts] / H[ts].sum(-1, keepdims=True)
    h = np.broadcast_to(h0[:, None, :], (E, K, h0.shape[1])).copy()
    kk = np.asarray(ks)
    def reb(mask):
        hm = h[:, mask]; Vm = hm.sum(-1)
        tr = np.abs(w * Vm[..., None] - hm); cost = (tr * c).sum(-1)
        h[:, mask] = w * (Vm - cost)[..., None]
    if (kk == 0).any(): reb(kk == 0)
    for j in range(1, horizon + 1):
        h *= (1.0 + R[ts + j])[:, None, :]
        m = kk == j
        if m.any(): reb(m)
    return np.log(h.sum(-1))
