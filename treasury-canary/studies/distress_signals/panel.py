"""Q-R panel machinery for SPEC v1 of studies/distress-signals.md.

Data come in as balanced matrices indexed [unit, period] (NaN = unusable);
`stack` turns them into long vectors over the usable cells. Regressions use
Frisch-Waugh-Lovell: y and g are residualised on the fixed effects and
controls once, so every bootstrap or permutation draw is cheap.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def stack(mats: dict[str, np.ndarray], mask: np.ndarray):
    """Long vectors of every matrix over cells where mask is True; plus the
    (unit, period) index of each row."""
    u, t = np.nonzero(mask)
    return {k: v[u, t] for k, v in mats.items()}, u, t


def dummies(idx: np.ndarray, drop_first: bool = False) -> np.ndarray:
    levels = np.unique(idx)
    if drop_first:
        levels = levels[1:]
    return (idx[:, None] == levels[None, :]).astype(float)


def projector(X: np.ndarray):
    """Orthonormal basis of col(X) (rank-revealing via SVD)."""
    U, s, _ = np.linalg.svd(X, full_matrices=False)
    r = int((s > s[0] * 1e-10).sum()) if s.size else 0
    return U[:, :r], r


def resid(Q: np.ndarray, v: np.ndarray) -> np.ndarray:
    return v - Q @ (Q.T @ v)


class FWL:
    """y = X gamma + beta g + e, with X = fixed effects + controls; optional
    weights (WLS: every row scaled by sqrt(w))."""

    def __init__(self, y, g, X, clusters, weights=None):
        sw = np.ones_like(y) if weights is None else np.sqrt(weights)
        self.y, self.g, self.X = y * sw, g * sw, X * sw[:, None]
        self.Q, self.rank = projector(self.X)
        self.yt, self.gt = resid(self.Q, self.y), resid(self.Q, self.g)
        self.gg = float(self.gt @ self.gt)
        self.beta = float(self.gt @ self.yt) / self.gg
        self.e = self.yt - self.beta * self.gt
        self.n, self.k = len(y), self.rank + 1
        self.clusters = clusters

    def cr1_se(self, clusters=None, e=None, beta_gt=None) -> float:
        cl = self.clusters if clusters is None else clusters
        e = self.e if e is None else e
        G = len(np.unique(cl))
        s = np.bincount(np.unique(cl, return_inverse=True)[1], weights=self.gt * e)
        f = G / (G - 1) * (self.n - 1) / (self.n - self.k)
        return float(np.sqrt(f * (s @ s)) / self.gg)

    def t(self, clusters=None) -> float:
        return self.beta / self.cr1_se(clusters)

    def twoway_se(self, c1, c2) -> float:
        """Cameron-Gelbach-Miller two-way clustered SE (each CR1-scaled)."""
        inter = np.unique(np.stack([c1, c2], 1), axis=0, return_inverse=True)[1].ravel()
        v = self.cr1_se(c1) ** 2 + self.cr1_se(c2) ** 2 - self.cr1_se(inter) ** 2
        return float(np.sqrt(max(v, 0.0)))

    def driscoll_kraay_se(self, period, bandwidth) -> float:
        """Driscoll-Kraay SE: Newey-West over the period sums of g~ e."""
        per = np.unique(period, return_inverse=True)[1]
        h = np.bincount(per, weights=self.gt * self.e)
        S = h @ h
        for lag in range(1, bandwidth + 1):
            w = 1 - lag / (bandwidth + 1)
            S += 2 * w * (h[lag:] @ h[:-lag])
        return float(np.sqrt(max(S, 0.0)) / self.gg)


def wild_cluster_bootstrap(m: FWL, clusters: np.ndarray, draws: int, rng) -> dict:
    """Wild-cluster RESTRICTED bootstrap (beta = 0 imposed), Webb six-point
    weights, statistic t = beta / CR1 SE with these clusters. One-sided
    p = (1 + #{t* >= t}) / (1 + draws)."""
    labels, inv = np.unique(clusters, return_inverse=True)
    G = len(labels)
    t_obs = m.beta / m.cr1_se(clusters)
    u_r = m.yt                                   # residuals of the restricted model
    A_cols = []
    for c in range(G):
        a_c = resid(m.Q, np.where(inv == c, u_r, 0.0))
        A_cols.append(a_c)
    A_vec = np.stack(A_cols, 1)                  # n x G
    gA = m.gt @ A_vec                            # G
    Acc = np.stack([np.bincount(inv, weights=m.gt * A_vec[:, c], minlength=G) for c in range(G)], 1)
    Bc = np.bincount(inv, weights=m.gt * m.gt, minlength=G)
    f = G / (G - 1) * (m.n - 1) / (m.n - m.k)
    W = rng.choice(WEBB, size=(draws, G))
    beta_s = (W @ gA) / m.gg
    S = W @ Acc.T - beta_s[:, None] * Bc[None, :]       # draws x G cluster scores
    se_s = np.sqrt(f * (S * S).sum(1)) / m.gg
    t_s = beta_s / se_s
    return {"t": float(t_obs), "p": float((1 + np.sum(t_s >= t_obs)) / (1 + draws)),
            "draws": draws, "clusters": int(G)}


def freedman_lane_within(y_mat, g_mat, ctrl_mats, cells, unit_div, draws, rng,
                         weights_mat=None) -> dict:
    """Co-check: state FE + division x period FE + controls; residuals of the
    reduced model (no g) are permuted as WHOLE unit histories within
    divisions (same permutation every period); statistic studentised by the
    unit-clustered CR1 SE. Requires a balanced panel (cells all True)."""
    assert cells.all(), "Freedman-Lane needs a balanced panel"
    nU, nT = y_mat.shape
    u = np.repeat(np.arange(nU), nT)
    t = np.tile(np.arange(nT), nU)
    divs = np.asarray(unit_div)[u]
    dt_idx = np.unique(np.stack([divs, t.astype(str)], 1), axis=0, return_inverse=True)[1].ravel()
    X = np.column_stack([dummies(u), dummies(dt_idx, drop_first=True)] +
                        [c.ravel() for c in ctrl_mats])
    w = None if weights_mat is None else weights_mat.ravel()
    m = FWL(y_mat.ravel(), g_mat.ravel(), X, u, w)
    t_obs = m.t(u)
    sw = np.ones(nU * nT) if w is None else np.sqrt(w)
    r = m.yt.reshape(nU, nT)                     # reduced-model residuals (weighted scale)
    # within-division permutations of unit histories
    groups = {}
    for i, d in enumerate(unit_div):
        groups.setdefault(d, []).append(i)
    count = 0
    batch = 250
    done = 0
    while done < draws:
        b = min(batch, draws - done)
        V = np.empty((nU * nT, b))
        for j in range(b):
            perm = np.arange(nU)
            for idx in groups.values():
                perm[idx] = rng.permutation(idx)
            V[:, j] = r[perm].ravel()
        MV = V - m.Q @ (m.Q.T @ V)
        beta_s = (m.gt @ MV) / m.gg
        E = MV - np.outer(m.gt, beta_s)
        G = nU
        f = G / (G - 1) * (m.n - 1) / (m.n - m.k)
        Sc = np.stack([np.bincount(u, weights=m.gt * E[:, j], minlength=nU) for j in range(b)], 1)
        se_s = np.sqrt(f * (Sc * Sc).sum(0)) / m.gg
        count += int(np.sum(beta_s / se_s >= t_obs))
        done += b
    return {"beta": m.beta, "t": float(t_obs), "p": (1 + count) / (1 + draws), "draws": draws}


def clark_west(e0: np.ndarray, e1: np.ndarray, f0: np.ndarray, f1: np.ndarray,
               origin: np.ndarray, nw_lags: int = 4, horizon: int = 4) -> dict:
    """Clark-West (2007) adjusted MSPE for nested models (0 = without g).
    f(s,t) = e0^2 - [e1^2 - (f0 - f1)^2], averaged over states per origin;
    one-sided t on the origin series with Newey-West SE and the
    Harvey-Leybourne-Newbold small-sample correction, t(n-1) reference."""
    adj = e0 ** 2 - (e1 ** 2 - (f0 - f1) ** 2)
    org = np.unique(origin)
    fbar = np.array([adj[origin == o].mean() for o in org])
    n = len(fbar)
    d = fbar - fbar.mean()
    S = d @ d / n
    for lag in range(1, nw_lags + 1):
        S += 2 * (1 - lag / (nw_lags + 1)) * (d[lag:] @ d[:-lag]) / n
    tstat = fbar.mean() / np.sqrt(S / n)
    h = horizon                                   # forecast horizon for HLN
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    t_adj = tstat * hln
    return {"origins": int(n), "cw_mean": float(fbar.mean()), "t": float(t_adj),
            "p": float(1 - stats.t.cdf(t_adj, n - 1)),
            "mse_ratio": float(np.mean(e1 ** 2) / np.mean(e0 ** 2))}
