"""SYNTHETIC ONLY. Size and power of the SPEC v0 D-1 decision rule, and D-3 at n=12.
No data file is read. Model (per firing f):
  m_f = |E_f| drawn from the in-sample DTWEXBGS set (counts only, review_stats_work/insample_counts.py)
  with prob pi_hom the episode is homogeneous (all E_f days miss or all hit) -> D_f = 0 exactly
  else others' hit rate p- ~ Beta(1.64, 3.05) (mean 0.35, sd 0.20); rule's hit prob q = min(1, p- + delta)
  S1_f correlated within cluster via a Gaussian factor (rho); p_f = (S1_f + (m-1) p-)/m (firing day in E_f)
  D_f = S1_f - p_f ; D_c = mean_f D_f ; T = mean_c D_c
D-1 classes per SPEC section 4: PASS = T>=0.15 & p<=0.05 & all LOO T>0 & share(D_c>0)>=0.60;
FAIL = T<0.05 and not INVERSE; INVERSE = T<=-0.10 & lower p<=0.05; else INCONCLUSIVE."""
import numpy as np
from scipy.stats import norm, binom

rng = np.random.default_rng(20261102)
EF_SIZES = np.array([121, 37, 80, 65, 43, 71, 60, 50, 3, 10, 51, 26, 133, 1])
A_, B_ = 1.64, 3.05
SIGN_CACHE = {}


def signs(K):
    if K not in SIGN_CACHE:
        if K <= 16:
            M = ((np.arange(2 ** K)[:, None] >> np.arange(K)) & 1) * 2 - 1
        else:
            M = rng.choice([-1, 1], size=(20000, K))
        SIGN_CACHE[K] = M.astype(float)
    return SIGN_CACHE[K]


def signflip_p(D, upper=True):
    M = signs(len(D))
    Tstar = M @ D / len(D)
    T = D.mean()
    if upper:
        return np.mean(Tstar >= T - 1e-12)
    return np.mean(Tstar <= T + 1e-12)


def cluster_sizes(K, kind):
    if kind == "single":
        return np.ones(K, int)
    # mixed: 40% singletons, 20% 2-3, 20% 4-8, 20% 9-15  (mean ~4.6)
    u = rng.random(K)
    return np.where(u < .4, 1, np.where(u < .6, rng.integers(2, 4, K), np.where(u < .8, rng.integers(4, 9, K), rng.integers(9, 16, K))))


def one_rep(K, kind, delta, pi_hom, rho, pfix=None):
    Dc = np.empty(K)
    for c, n in enumerate(cluster_sizes(K, kind)):
        m = rng.choice(EF_SIZES, n)
        pm = np.full(n, pfix) if pfix is not None else rng.beta(A_, B_, n)
        hom = rng.random(n) < pi_hom
        q = np.minimum(1.0, pm + delta)
        z = np.sqrt(rho) * rng.standard_normal() + np.sqrt(1 - rho) * rng.standard_normal(n)
        S = (norm.cdf(z) < q).astype(float)
        p_f = (S + (m - 1) * pm) / m
        D = np.where(hom, 0.0, S - p_f)
        Dc[c] = D.mean()
    return Dc


def classify(Dc):
    K = len(Dc); T = Dc.mean()
    p_up = signflip_p(Dc, True)
    loo = (K * T - Dc) / (K - 1)
    share = np.mean(Dc > 0)
    passed = (T >= 0.15) and (p_up <= 0.05) and np.all(loo > 0) and (share >= 0.60)
    inverse = (T <= -0.10) and (signflip_p(Dc, False) <= 0.05)
    fail = (T < 0.05) and not inverse
    return dict(T=T, p05=p_up <= 0.05, Tbar=T >= 0.15, share=share >= 0.60, loo=bool(np.all(loo > 0)),
                PASS=passed, FAIL=fail, INVERSE=inverse, INC=not (passed or fail or inverse), sdDc=Dc.std(ddof=1))


def scenario(K, kind, delta, pi_hom, rho, reps, pfix=None):
    R = [classify(one_rep(K, kind, delta, pi_hom, rho, pfix)) for _ in range(reps)]
    agg = {k: np.mean([r[k] for r in R]) for k in R[0]}
    return agg


if __name__ == "__main__":
    import sys
    reps0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    print("=== D-1 under H0 (delta=0): size of the 'exact' sign-flip and class rates ===")
    print("K  kind    pi_hom rho   p<=.05  PASS   INVERSE FAIL   sd(D_c)")
    for K in (15, 20, 25, 35):
        for kind in ("single", "mixed"):
            for pi_hom in (0.0, 0.25):
                a = scenario(K, kind, 0.0, pi_hom, 0.3, reps0 * 2)
                print(f"{K:<3}{kind:<8}{pi_hom:<7}{0.3:<6}{a['p05']:.3f}   {a['PASS']:.3f}  {a['INVERSE']:.3f}   {a['FAIL']:.3f}  {a['sdDc']:.2f}")
    print("\nfixed p=0.30, singletons, no homogeneity, rho irrelevant (max skew):")
    for K in (15, 20, 25, 35):
        a = scenario(K, "single", 0.0, 0.0, 0.0, reps0 * 2, pfix=0.30)
        b = scenario(K, "single", 0.0, 0.0, 0.0, reps0 * 2, pfix=0.65)
        print(f"  K={K}: size at p_f=0.30 {a['p05']:.3f} ; at p_f=0.65 {b['p05']:.3f}")

    print("\n=== D-1 power: delta = rule's edge in MIXED episodes (q = p- + delta) ===")
    print("K  kind   pi_hom delta  E[T]   sdDc  p<=.05 T>=.15 share>=.6 LOO   PASS   FAIL   INC")
    for K in (20, 25, 35):
        for kind in ("mixed", "single"):
            for pi_hom in (0.0, 0.25):
                for delta in (0.10, 0.15, 0.20, 0.25, 0.30):
                    a = scenario(K, kind, delta, pi_hom, 0.3, reps0)
                    print(f"{K:<3}{kind:<7}{pi_hom:<7}{delta:<7}{a['T']:+.3f} {a['sdDc']:.2f}  {a['p05']:.2f}   {a['Tbar']:.2f}   {a['share']:.2f}     {a['loo']:.2f}  {a['PASS']:.2f}   {a['FAIL']:.2f}   {a['INC']:.2f}")

    print("\n=== D-3 forward at n=12 firings (each its own cluster), p_f fixed 0.35 ===")
    for q in (0.35, 0.50, 0.60, 0.70):
        for pi_hom in (0.0, 0.25):
            # D-3 PASS is only T>=.15 & sign-flip p<=.05 (no LOO/share condition)
            R = []
            for _ in range(reps0 * 2):
                Dc = one_rep(12, "single", q - 0.35, pi_hom, 0.0, pfix=0.35)
                R.append((Dc.mean() >= 0.15) and (signflip_p(Dc, True) <= 0.05))
            print(f"  q={q:.2f} pi_hom={pi_hom}: D-3 PASS rate at n=12 = {np.mean(R):.3f}")
    # the SPEC's section 2.1 basis: exact one-sample binomial vs p0=0.35, alpha .05 one-sided
    for q, n in ((0.70, 12), (0.60, 23), (0.50, 65)):
        crit = binom.ppf(0.95, n, 0.35) + 1           # smallest x with P(X>=x|p0) <= .05
        while binom.sf(crit - 1, n, 0.35) > 0.05:
            crit += 1
        print(f"  binomial basis: n={n}, q={q}: exact power {binom.sf(crit - 1, n, q):.2f} (normal-approx n for 80% shown in SPEC)")
