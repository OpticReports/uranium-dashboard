"""Exact operating characteristics of the D-3 group-sequential rule under equal null probability p0.
Looks at n = 8, 16, 24 matured units; PASS if one-sided exact p <= alpha_j; FAIL if 95% upper bound on delta < 0.10."""
from math import comb
LOOKS=[(8,0.005),(16,0.015),(24,0.030)]
def pmf(n,p): return [comb(n,k)*p**k*(1-p)**(n-k) for k in range(n+1)]
def sf(n,p,s): return sum(pmf(n,p)[s:])
def cdf(n,p,s): return sum(pmf(n,p)[:s+1])
def delta_U(n,p0,s):
    # largest delta with P(S<=s | p0+delta) >= 0.05
    d=0.0; best=-p0
    for i in range(0,1001):
        dd=-p0+i*(1.0)/1000
        q=min(max(p0+dd,0),1)
        if cdf(n,q,s)>=0.05: best=dd
    return best
def oc(p0,delta,paths=None):
    # exact by enumerating increments between looks
    q=min(p0+delta,1)
    # state: dict s->prob of continuing with s hits at current n
    states={0:1.0}; n_prev=0; P=F=0.0; out=[]
    for n,a in LOOKS:
        m=n-n_prev; inc=pmf(m,q); new={}
        for s,pr in states.items():
            for j,pj in enumerate(inc): new[s+j]=new.get(s+j,0)+pr*pj
        cont={}
        for s,pr in new.items():
            if sf(n,p0,s)<=a: P+=pr
            elif delta_U(n,p0,s)<0.10: F+=pr
            else: cont[s]=pr
        out.append((n,round(P,3),round(F,3)))
        states=cont; n_prev=n
    return out, round(1-P-F,3)
for p0 in (0.3,0.5):
    print('p0',p0)
    for d in (0,0.1,0.2,0.3,0.4,0.5):
        if p0+d<=1: print('  delta',d, oc(p0,d))
# min hits needed for PASS at each look
for p0 in (0.3,0.5):
    print(p0,[(n,min(s for s in range(n+1) if sf(n,p0,s)<=a)) for n,a in LOOKS], 'max hits for FAIL', [(n,max([s for s in range(n+1) if delta_U(n,p0,s)<0.10],default=None)) for n,a in LOOKS])
