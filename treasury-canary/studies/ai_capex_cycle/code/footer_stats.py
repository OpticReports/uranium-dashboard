import json, numpy as np, sys
eps=json.load(open(sys.argv[1]))
def sp(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); ra=np.argsort(np.argsort(a)); rb=np.argsort(np.argsort(b)); return np.corrcoef(ra,rb)[0,1]
print("n",len(eps))
print("Spearman corr10 vs vol: %.2f"%sp([e["corr10"] for e in eps],[e["vol"] for e in eps]))
print("Spearman fut_maxdd vs mkt_fut_maxdd: %.2f"%sp([e["fut_maxdd"] for e in eps],[e["mkt_fut_maxdd"] for e in eps]))
# calendar clusters: consecutive episode months sorted, new cluster if gap > 24 months
ms=sorted(int(e["month"][:4])*12+int(e["month"][4:]) for e in eps)
for gap in (12,24,36):
    cl=1
    for a,b in zip(ms,ms[1:]):
        if b-a>gap: cl+=1
    print(f"calendar clusters (gap>{gap}m): {cl}")
# cluster id by 24m gap
ids={}; cid=0; prev=None
for e in sorted(eps,key=lambda e:e["month"]):
    m=int(e["month"][:4])*12+int(e["month"][4:])
    if prev is not None and m-prev>24: cid+=1
    ids[id(e)]=cid; prev=m
# logistic regression via Newton; features standardized? report raw-unit coefficients
def logit(X,y,iters=50):
    X=np.column_stack([np.ones(len(y)),X]); b=np.zeros(X.shape[1])
    for _ in range(iters):
        p=1/(1+np.exp(-X@b)); W=p*(1-p)
        H=X.T@(X*W[:,None])+1e-6*np.eye(X.shape[1]); g=X.T@(y-p)
        b=b+np.linalg.solve(H,g)
    return b
y=np.array([e["fut_maxdd"]>=.4 for e in eps],float)
feats={"raw24":[e["raw24"] for e in eps],"vol":[e["vol"] for e in eps],"accel":[e["accel"] for e in eps],"zero_corr":[1.0*(e["corr10"]==0) for e in eps]}
X=np.column_stack([feats[k] for k in feats]); names=list(feats)
b=logit(X,y); print("full-sample logit coefs (raw units):",dict(zip(["const"]+names,np.round(b,2))))
# standardized
Xs=(X-X.mean(0))/X.std(0); bs=logit(Xs,y); print("standardized:",dict(zip(["const"]+names,np.round(bs,2))))
rng=np.random.default_rng(0); clusters=np.array([ids[id(e)] for e in eps]); uc=np.unique(clusters)
B=[];Bs=[]
for _ in range(2000):
    pick=rng.choice(uc,len(uc),replace=True); idx=np.concatenate([np.where(clusters==c)[0] for c in pick])
    if y[idx].min()==y[idx].max(): continue
    try: B.append(logit(X[idx],y[idx])); Bs.append(logit((X[idx]-X.mean(0))/X.std(0),y[idx]))
    except Exception: pass
B=np.array(B); Bs=np.array(Bs)
for k,nm in enumerate(["const"]+names):
    print(f"  cluster-bootstrap 90% CI {nm:10s} raw-units [{np.percentile(B[:,k],5):+.2f}, {np.percentile(B[:,k],95):+.2f}]   standardized [{np.percentile(Bs[:,k],5):+.2f}, {np.percentile(Bs[:,k],95):+.2f}]")
# univariate raw24 only
B1=[]
for _ in range(2000):
    pick=rng.choice(uc,len(uc),replace=True); idx=np.concatenate([np.where(clusters==c)[0] for c in pick])
    if y[idx].min()==y[idx].max(): continue
    B1.append(logit(X[idx,[0]],y[idx])[1])
print("  univariate raw24 log-odds per unit, cluster-bootstrap 90%% CI [%.2f, %.2f], point %.2f"%(np.percentile(B1,5),np.percentile(B1,95),logit(X[:,[0]],y)[1]))
