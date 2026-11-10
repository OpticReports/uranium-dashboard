"""Parameter sensitivity of the real-time deceleration rule (same logic as scoping/code/decel_realtime.py)."""
import csv, os, numpy as np, itertools
RAW='<scratch>/dxy/scoping/raw'
def fredd(fid):
    o={}
    for r in csv.DictReader(open(os.path.join(RAW,fid+".csv"))):
        if r[fid] not in ("","."): o[r["observation_date"]]=float(r[fid])
    return o
bd=fredd("DTWEXBGS"); vix=fredd("VIXCLS"); y10=fredd("DGS10")
days=sorted(d for d in bd if d in vix and d in y10); B=np.array([bd[d] for d in days]); V=np.array([vix[d] for d in days]); Y=np.array([y10[d] for d in days])
def run(thr=0.04, frac=0.5, win=60, near=0.97, cool=120, yieldcond=True):
    roc=np.full(len(B),np.nan)
    for k in range(20,len(B)): roc[k]=B[k]/B[k-20]-1
    fires=[]; last=-999
    for k in range(win+20,len(B)-1):
        mx=np.nanmax(roc[k-win:k+1]); kmx=k-win+int(np.nanargmax(roc[k-win:k+1]))
        yc = (Y[k]<Y[max(0,kmx-20)]) if yieldcond else True
        if mx>=thr and roc[k]<=frac*mx and B[k]>=near*max(B[k-win:k+1]) and yc and k-last>cool:
            last=k
            pk=k+int(np.argmax(B[k:min(len(B),k+250)]))
            fires.append((days[k], round(100*(B[pk]/B[k]-1),1), round(float(V[min(len(V)-1,k+60)]-V[k]),1)))
    return fires
base=run()
print("BASE", len(base), base)
for thr in (0.03,0.035,0.04,0.05):
  for frac in (0.4,0.5,0.6):
    for win in (40,60,90):
      f=run(thr,frac,win)
      good=sum(1 for x in f if x[1]<3 and x[2]<0); bad=sum(1 for x in f if x[1]>=3 or x[2]>0)
      print(f"thr={thr} frac={frac} win={win}: n={len(f)} ok(dollar<+3% & vix down)={good} fail={bad}  dates={[x[0] for x in f]}")
print("no yield condition:", run(yieldcond=False))
