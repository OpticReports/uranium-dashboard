import csv, sys, io, collections
rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8')))
print("n", len(rows))
for r in rows[:3]: print({k: r[k] for k in ('CURR_DENOM','BORROWERS_CTY','BORROWERS_SECTOR','LENDERS_SECTOR','L_POS_TYPE','L_INSTR','UNIT_MEASURE','TIME_PERIOD','OBS_VALUE','TITLE')})
# list USD series keys
for r in rows:
    if r['CURR_DENOM']=='USD' and r['UNIT_MEASURE'] in ('USD','771','USD_R_B1GQ') :
        print(r['FREQ'],r['CURR_DENOM'],r['BORROWERS_CTY'],r['BORROWERS_SECTOR'],r['LENDERS_SECTOR'],r['L_POS_TYPE'],r['L_INSTR'],r['UNIT_MEASURE'],'|',r['TIME_PERIOD'],r['OBS_VALUE'],'|',r['TITLE'][:110])
