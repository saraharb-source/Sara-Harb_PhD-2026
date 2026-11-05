"""Coupling verification: each Module 2 recipe is annualized, written into the Module 1 EAF stage through the
shared register (coupling.py), and the resulting EAF footprint, crude-steel direct emissions and rebar
chargeable emissions are compared with the S1, S2, S3 and baseline scenario sets of Module 1.
Usage: python coupling_verify.py [--m1 <file>] [--m2 <file>]"""
import paths
import module1_engine as E
from module2_engine import load_params
from coupling import recipe_to_m1
d = paths.module1_rows(); P = load_params(paths.M2)
base = d['Baseline']; base_up = E.run(base)['upstream_ghg_kg']
recipes = {
 'S1': dict(hdri=0, cdri=0, hms1=101.111111111111, hms2=85.1851851851852, gas=12, hms1_row=11, hms2_row=16, cao_row=20, mgo_row=29, c_row=40),
 'S2': dict(hdri=0, cdri=0, hms1=109.677419354839, hms2=65.1685393258427, gas=11, hms1_row=12, hms2_row=15, cao_row=23, mgo_row=29, c_row=38),
 'S3': dict(hdri=23.05, cdri=0, hms1=49.96584, hms2=110.382051764706, gas=12, hms1_row=11, hms2_row=14, cao_row=21, mgo_row=29, c_row=40),
 'BL': dict(hdri=0, cdri=23.0494287687006, hms1=91.113745467319, hms2=60.7401598294255, gas=5, cdri_row=10, hms1_row=12, hms2_row=15, cao_row=20, mgo_row=32, c_row=42),
}
ref = {'S1': (47570, 6496.38, 4406.4), 'S2': (32832, 4596.05, 2506.1), 'S3': (59532, 7013.10, 8889.7), 'BL': (55515, 3538.90, 5415.4)}
ok = True
for k, rcp in recipes.items():
    sc, o = recipe_to_m1(base, P, rcp)
    r = E.run(sc, base_upstream_ghg=base_up)
    eaf = r['stage_ghg_t']['EAF']
    print(f"{k:3s} EAF footprint {eaf:7,.0f} t CO2e (Module 1 {ref[k][0]:,})  crude direct {r['crude']['direct']:8.2f} t (Module 1 {ref[k][1]:,.2f})  rebar chargeable {r['hr']['chargeable']:7.1f} t (Module 1 {ref[k][2]:,.1f})")
    ok &= abs(eaf - ref[k][0]) < 1 and abs(r['crude']['direct'] - ref[k][1]) < 0.01 and abs(r['hr']['chargeable'] - ref[k][2]) < 0.1
print('coupling reproduces the four Module 1 scenario sets' if ok else 'MISMATCH')
raise SystemExit(0 if ok else 1)
