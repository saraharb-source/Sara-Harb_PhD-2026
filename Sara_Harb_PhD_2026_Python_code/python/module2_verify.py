"""Module 2 verification, in two parts.

1. Recipes.  The baseline and the four optimized recipes held in the workbook tabs are evaluated by
   module2_engine; total cost (USD a heat) and emissions (t CO2e a heat) are compared with the TOTAL row of
   each tab (F116:G116 on the baseline tab, F124:G124 on the optimization tabs).
2. Search.  module2_search runs the four objectives from scratch over the 17,496 supplier combinations and
   reports the optimum it finds against the workbook tab, together with the size of the feasible set and of
   the Pareto frontier.

3. Wider search (--wide).  DRI is also allowed to enter the charge: hot DRI from the own plant from 0 to 23 t a
   heat in 1 t steps, and cooled DRI from any of the four CDRI sources from 0 to 120 t a heat in 2 t steps.  The
   lowest-cost and lowest-emission optima are compared with those of the reference search.  (About 15 minutes.)

Usage: python module2_verify.py [--m2 <file>] [--no-search] [--wide]"""
import sys, json, time, warnings
warnings.filterwarnings('ignore')
import numpy as np
import openpyxl
import paths
from module2_engine import load_params, evaluate
from module2_search import optimize, enumerate_frontier, n_combinations

# tab, TOTAL row, recipe (t a heat; Nm3/t; rows of 'Suppliers Pool')
CASES = {
    'Baseline': ('Baseline Calculation Engine', 116,
                 dict(hdri=0, cdri=23.0494287687006, hms1=91.113745467319, hms2=60.7401598294255, gas=5,
                      cdri_row=10, hms1_row=12, hms2_row=15, cao_row=20, mgo_row=32, c_row=42)),
    'Lowest cost': ('Optimization – Lowest Cost', 124,
                    dict(hdri=0, cdri=0, hms1=101.111111111111, hms2=85.1851851851852, gas=12,
                         cdri_row=7, hms1_row=11, hms2_row=16, cao_row=20, mgo_row=29, c_row=40)),
    'Lowest emissions': ('Optimization – Lowest Emissions', 124,
                         dict(hdri=0, cdri=0, hms1=109.677419354839, hms2=65.1685393258427, gas=11,
                              cdri_row=7, hms1_row=12, hms2_row=15, cao_row=23, mgo_row=29, c_row=38)),
    'Balanced': ('Optimization – Balanced', 124,
                 dict(hdri=0, cdri=0, hms1=110, hms2=71.7647058823529, gas=11,
                      cdri_row=7, hms1_row=11, hms2_row=14, cao_row=23, mgo_row=29, c_row=38)),
    'HDRI floor': ('Opt – Lowest Cost (HDRI floor)', 124,
                   dict(hdri=23.05, cdri=0, hms1=49.96584, hms2=110.382051764706, gas=12,
                        cdri_row=7, hms1_row=11, hms2_row=14, cao_row=21, mgo_row=29, c_row=40)),
}
KEYS = ('hms1_row', 'hms2_row', 'cao_row', 'mgo_row', 'c_row')


def main(search=True):
    P = load_params(paths.M2)
    wb = openpyxl.load_workbook(paths.M2, data_only=True)
    ref, ok_all, res = {}, True, {}
    print('1. Recipes held in the workbook')
    for k, (tab, row, rc) in CASES.items():
        ws = wb[tab]
        ref[k] = (ws[f'F{row}'].value, ws[f'G{row}'].value)
        held = [ws[f'C{r}'].value for r in (18, 19, 20, 21)]
        assert max(abs(a - b) for a, b in zip(held, (rc['hdri'], rc['cdri'], rc['hms1'], rc['hms2'])) ) < 1e-6, (k, held)
        o = evaluate(P, **rc)
        dc, dg = float(o['cost']) - ref[k][0], float(o['ghg']) - ref[k][1]
        ok = abs(dc) < 1e-6 and abs(dg) < 1e-9 and bool(o['feasible'])
        ok_all &= ok
        res[k] = dict(cost=float(o['cost']), ghg=float(o['ghg']), workbook=ref[k], feasible=bool(o['feasible']))
        print(f"   {k:17s} cost {float(o['cost']):10,.2f} (workbook {ref[k][0]:10,.2f})  "
              f"emissions {float(o['ghg']):7.3f} (workbook {ref[k][1]:7.3f})  all checks met: {bool(o['feasible'])}  "
              f"{'OK' if ok else 'MISMATCH'}")
    if search:
        print(f'2. Search over {n_combinations():,} supplier combinations')
        t0 = time.time()
        runs = {'Lowest cost': dict(objective='cost'), 'Lowest emissions': dict(objective='ghg')}
        found = {k: optimize(P, **a) for k, a in runs.items()}
        found['Balanced'] = optimize(P, 'ghg', cost_cap=1.02 * found['Lowest cost']['cost'])
        found['HDRI floor'] = optimize(P, 'cost', hdri=23.05)
        for k, b in found.items():
            rc = CASES[k][2]
            same = all(b[x] == rc[x] for x in KEYS)
            rel = abs(b['cost'] - ref[k][0]) / ref[k][0]
            ok = same and rel < 1e-5
            ok_all &= ok
            res[k]['search'] = {x: b[x] for x in ('cost', 'ghg', 'hms1_t', 'hms2_t', 'gas', 'names')}
            print(f"   {k:17s} cost {b['cost']:10,.2f}  emissions {b['ghg']:7.3f}  same suppliers as the tab: {same}  "
                  f"cost difference {100 * rel:.4f}%  {'OK' if ok else 'MISMATCH'}")
        pts, front = enumerate_frontier(P)
        res['frontier'] = dict(feasible=int(len(pts)), non_dominated=int(len(front)), front=front.tolist())
        print(f'   feasible recipes {len(pts):,}; non-dominated {len(front)}   ({time.time() - t0:.0f} s)')
    if search and '--wide' in sys.argv:
        print('3. Wider search with DRI allowed to enter the charge')
        t0 = time.time()
        for k, obj in (('Lowest cost', 'cost'), ('Lowest emissions', 'ghg')):
            cands = [optimize(P, obj, hdri=float(h)) for h in np.arange(0, 23.01, 1.0)]
            cands += [optimize(P, obj, cdri_grid=tuple(np.arange(2, 120.01, 2.0)))]
            b = min((c for c in cands if c), key=lambda c: c['obj'])
            same = abs(b['obj'] - found[k]['obj']) < 1e-6
            ok_all &= same
            res[k]['wide'] = {x: b[x] for x in ('cost', 'ghg', 'hdri', 'cdri_t', 'names')}
            print(f"   {k:17s} cost {b['cost']:10,.2f}  emissions {b['ghg']:7.3f}  HDRI {b['hdri']:.0f} t  "
                  f"CDRI {b['cdri_t']:.0f} t  same optimum as the reference search: {same}  ({time.time() - t0:.0f} s)")
    json.dump(res, open(paths.out('module2_verify.json'), 'w'), indent=1, default=float)
    return ok_all


if __name__ == '__main__':
    raise SystemExit(0 if main('--no-search' not in sys.argv) else 1)
