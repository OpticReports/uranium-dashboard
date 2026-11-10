import json, pandas as pd, numpy as np
B='/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/blocks/event'
D='/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/data'
n=json.load(open(f'{B}/numbers.json')); m=json.load(open('mine.json'))
V=lambda k: n[k]['value'] if isinstance(n.get(k),dict) and 'value' in n[k] else n.get(k)
bad=[]; ok=0
def chk(k,mine,tol=0):
    global ok
    b=V(k)
    if isinstance(mine,float) and isinstance(b,(int,float)):
        if abs(mine-b)>1e-4+tol: bad.append((k,b,mine))
        else: ok+=1
    else:
        if b!=mine: bad.append((k,b,mine))
        else: ok+=1
rules=['D1-RED','D1-YELLOW','D2','D3-RED','D3-YELLOW','PPI-RED','PPI-D2']
for h in (12,18):
    chk(f'base_rate_common_h{h}', m['nber'][f'D1-RED_h{h}']['base'])
    for r in rules:
        x=m['nber'][f'{r}_h{h}']; k=f'{r}_h{h}'
        chk(k+'_hits',x['hits']); chk(k+'_false_positives',x['fp']); chk(k+'_coincident',x['coinc']); chk(k+'_pending',x['pending'])
        chk(k+'_episode_precision',x['ep_prec']); chk(k+'_recall_caught',int(x['recall'].split('/')[0])); chk(k+'_recall_evaluable',int(x['recall'].split('/')[1]))
        chk(k+'_month_precision',x['month_prec']); chk(k+'_month_precision_n_on',x['month_n']); chk(k+'_base_rate',x['base'])
        chk(k+'_false_positive_names',x['fps']); chk(k+'_coincident_names',x['coincs'])
        chk(k+'_event_categories',{e:v.lower() for e,v in x['per_event'].items()})
        # leads: mine: hit lead from episode; coincident lead negative
        leads={}
        for e,v in x['per_event'].items():
            leads[e]=None
        for ep in x['episodes']:
            for e in ep['events']:
                if leads.get(e) is None: leads[e]=(pd.Period(e,'M')-pd.Period(ep['raw'].split('..')[0],'M')).n
            for e in ep['coinc']:
                if ep['outcome']=='COINCIDENT' and leads.get(e) is None: leads[e]=(pd.Period(e,'M')-pd.Period(ep['raw'].split('..')[0],'M')).n
        chk(k+'_event_leads',leads)
        chk(k+'_episodes',len(x['episodes']))
        hits=[f"{ep['start']}→{','.join(ep['events'])}" if len(ep['events'])==1 else f"{ep['start']}→{', '.join(ep['events'])}" for ep in x['episodes'] if ep['outcome']=='HIT']
        b=V(k+'_hit_names'); 
        if b!=hits: bad.append((k+'_hit_names',b,hits))
        else: ok+=1
# episode lists with peaks
p=pd.read_csv(f'{D}/panel.csv',parse_dates=['date']); p['m']=p['date'].dt.to_period('M'); p=p.set_index('m')
col={'D1-RED':'oil_12m_pct','D1-YELLOW':'oil_12m_pct','D2':'nopi36_sum12','D3-RED':'real_oil_12m_pct','D3-YELLOW':'real_oil_12m_pct','PPI-RED':'ppi_crude_12m_pct','PPI-D2':'ppi_nopi36_sum12'}
thr={'D1-RED':50,'D1-YELLOW':25,'D2':10,'D3-RED':50,'D3-YELLOW':25,'PPI-RED':50,'PPI-D2':10}
for r in rules:
    s=p[col[r]]; on=(s>=thr[r])&s.notna(); months=list(on.index[on.values]); eps=[]; cur=[]
    for mm in months:
        if cur and (mm-cur[-1]).n-1>6: eps.append(cur); cur=[]
        cur.append(mm)
    if cur: eps.append(cur)
    mine=[]
    for ep in eps:
        free=[x for x in ep if p.loc[x,'usrec']==0]; pk=s.loc[ep[0]:ep[-1]]; pk=pk[pk>=thr[r]]
        mine.append(dict(start=str(free[0]) if free else '—',end=str(free[-1]) if free else '—',n_on0=len(free),raw_span=f'{ep[0]}..{ep[-1]}',n_on=len(ep),peak=round(float(s.loc[ep].max()),2),peak_month=str(s.loc[ep].idxmax())))
    b=V(f'episodes_{r}')
    if b!=mine:
        for i,(x,y) in enumerate(zip(b,mine)):
            if x!=y: bad.append((f'episodes_{r}[{i}]',x,y))
        if len(b)!=len(mine): bad.append((f'episodes_{r} len',len(b),len(mine)))
    else: ok+=1
print('OK',ok,'BAD',len(bad))
for b in bad: print(b)
# curve5 keys
ck=[k for k in n if k.startswith('curve5')]
print('n curve5 keys',len(ck)); print(ck[:12])
import re
cb=[]; cok=0
for k in ck:
    mm=re.match(r'curve5_(NBER|B1|B2)_(.+)_h(12|18)_(month_precision|recall|episode_precision|base|caught|false_positives|coincident|pending|month_n|hits|fp)$',k)
    if not mm: continue
    tgt,rule,h,stat=mm.groups(); rule=rule.replace('_',' ')
    x=m['curve'].get(f'{tgt}|{rule}|h{h}')
    if x is None: print('no match',k); continue
    mine={'month_precision':x['month_prec'],'recall':x['recall'],'episode_precision':(round(x['hits']/(x['hits']+x['fp']),4) if x['hits']+x['fp'] else None),'base':x['base'],'caught':x['caught'],'false_positives':x['fps'],'coincident':x['coincs'],'pending':x['pending'],'month_n':x['month_n'],'hits':x['hits'],'fp':x['fp']}[stat]
    b=V(k)
    if isinstance(mine,float) and isinstance(b,(int,float)): 
        if abs(mine-b)>1e-4: cb.append((k,b,mine))
        else: cok+=1
    elif b!=mine: cb.append((k,b,mine))
    else: cok+=1
print('curve5 OK',cok,'BAD',len(cb))
for b in cb: print(b)
unmatched=[k for k in ck if not re.match(r'curve5_(NBER|B1|B2)_(.+)_h(12|18)_(month_precision|recall|episode_precision|base|caught|false_positives|coincident|pending|month_n|hits|fp)$',k)]
print('unmatched curve5 keys',unmatched[:30])
