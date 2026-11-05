"""Chapter 6 re-optimization when a limit changes so that DRI must enter the charge.

(a) Supplier concentration cap at 40%: every purchased metallic is limited to 40% of the 121,000 t/yr metallic
    requirement (48,400 t/yr).  Solved as on the 'Supplier Cap Sensitivity' tab: DRI free to enter hot from the
    own plant (up to its output) or cooled from any of the four sources, scanned on a coarse grid and refined to
    0.02 t (module2_search.optimize_with_dri).  Results are compared with the tab.
(b) Hot-rolled coil grade (copper at most 0.08%): cooled DRI from any of the four sources in 2 t steps from
    0 to 120 t a heat, as reported in Chapter 6.

Usage: python sensitivity_supplier_cap_and_grade.py [--m2 <file>]   (about one hour)"""
import json, copy, time
import numpy as np
import openpyxl
import paths
from module2_engine import load_params
from module2_search import optimize, optimize_with_dri

P0 = load_params(paths.M2)
out = {}
t0 = time.time()

# (a) supplier cap 40%
tab = openpyxl.load_workbook(paths.M2, data_only=True)['Supplier Cap Sensitivity']
ref = {'cost': (tab['B11'].value, tab['B12'].value), 'ghg': (tab['B15'].value, tab['B16'].value)}
P = copy.deepcopy(P0)
for r in (7, 8, 9, 11, 12, 13, 14, 15, 16):            # merchant DRI and all scrap suppliers
    P['pool'][r]['N'] = 0.4 * 121000
out['cap_0.4'] = {}
for obj in ('cost', 'ghg'):
    b = optimize_with_dri(P, obj)
    out['cap_0.4'][obj] = dict(b, workbook=ref[obj])
    print(f"cap 40%, lowest {obj:4s}: cost {b['cost']:10,.2f} (tab {ref[obj][0]:10,.2f})  emissions {b['ghg']:7.2f} "
          f"(tab {ref[obj][1]:7.2f})  HDRI {b['hdri']:.2f} t  CDRI {b['cdri_t']:.2f} t {b['names']['cdri']}  "
          f"({time.time() - t0:.0f} s)", flush=True)

# (b) hot-rolled coil grade
P = copy.deepcopy(P0); P['B13'] = 'Hot Rolled Coil (HRC)'
out['grade_HRC'] = {}
for obj in ('cost', 'ghg'):
    b = optimize(P, obj, cdri_grid=tuple(np.arange(2, 120.01, 2.0)))
    out['grade_HRC'][obj] = b
    print(f"HRC grade, lowest {obj:4s}: cost {b['cost']:10,.2f}  emissions {b['ghg']:7.2f}  "
          f"CDRI {b['cdri_t']:.0f} t {b['names']['cdri']}  ({time.time() - t0:.0f} s)", flush=True)

json.dump(out, open(paths.out('sensitivity_supplier_cap_and_grade.json'), 'w'), indent=1, default=float)
