"""Chapter 6 sensitivity suite: (A) Module 1 one-at-a-time, grid-factor sweep, certificate price by reporting
year and the free-allocation phase-out, and a Monte Carlo of joint uncertainty with Spearman ranking;
(B) Module 2 recipe-level one-at-a-time; (C) re-optimization under changed conditions; (D) internal carbon
price; (E) DRI-share sweep coupled to Module 1; and the Pareto frontier of the reference case.
Usage: python sensitivity_chapter6.py [--m1 <file>] [--m2 <file>]   (several minutes)"""
import json, copy, time
import numpy as np
import paths
import module1_engine as E
from module2_engine import load_params, evaluate, set_tier
from module2_search import optimize as optimise, enumerate_frontier
from coupling import recipe_to_m1

d = paths.module1_rows(); P0 = load_params(paths.M2); OUT = paths.out('sensitivity_chapter6.json')
R = {}
base_up = {sc: E.run(d[sc])['upstream_ghg_kg'] for sc in d}
SCN = {'Baseline': 'Baseline', 'S1': 'S1 Lowest cost', 'S2': 'S2 Lowest GHG', 'S3': 'S3 HDRI floor'}


def m1(sc, p=None):
    r = E.run(d[sc], p, base_upstream_ghg=base_up[sc])
    return dict(chargeable=r['hr']['chargeable'], cert=r['hr']['cert'], see=r['hr']['see'], cum_bm=r['hr']['cum_bm'],
                billet_chg=r['crude']['chargeable'], dri_see=r['dr']['see'], footprint=r['chain_corrected_t'] / 100.0,
                footprint_t=r['chain_corrected_t'], crude_direct=r['crude']['direct'])

def ngp(f):
    """natural-gas carbon content scaled by f, with the LCA gas factor it implies (0.32 upstream + 2.053675 combustion)"""
    return {'ng_carbon': 0.5601 * f, 'ng_lca_ef': 0.32 + 2.053675 * f}


# ---------------------------------------------------------------- A. Module 1 one-at-a-time
M1_PARAMS = [
    ('grid_ef', 'Grid electricity emission factor', 450.0),
    ('ng_carbon', 'Natural-gas carbon content / combustion factor', 0.5601),
    ('dr_gas_mult', 'Natural gas used by the DR plant', 1.0),
    ('reheat_gas_mult', 'Reheating-furnace gas (rolling mill)', 1.0),
    ('bm_mult', 'CBAM product benchmarks', 1.0),
    ('free_alloc', 'Free-allocation share (CBAM factor)', 0.975),
    ('cert_price', 'Certificate price', 85.09),
    ('precursor_mult', 'Purchased-precursor (ferroalloy) values', 1.0),
    ('scrap_c_mult', 'Carbon content of scrap', 1.0),
    ('alloy_mult', 'Ferroalloy and aluminium emission factors', 1.0),
]
A = {}
for sc in ('Baseline', 'S2'):
    base = m1(sc); A[sc] = {'base': base, 'params': {}}
    for key, label, b in M1_PARAMS:
        rec = {'label': label, 'base_value': b}
        for pct in (-20, -10, 10, 20):
            v = b * (1 + pct / 100)
            if key == 'ng_carbon':      # carbon content x f moves the CBAM fuel emissions and the LCA gas factor together
                rec[pct] = m1(sc, ngp(1 + pct / 100))
            else:
                rec[pct] = m1(sc, {key: v})
        # elasticity (central difference, +/-10%)
        rec['S'] = {}
        for y in ('chargeable', 'cert', 'see', 'footprint'):
            y0 = base[y]
            if abs(y0) < 1e-12:
                rec['S'][y] = None
            else:
                rec['S'][y] = ((rec[10][y] - rec[-10][y]) / y0) / 0.2
        A[sc]['params'][key] = rec
R['m1_oat'] = A

# grid factor sweep (named values)
GRID = [(340, 'EU average (Dinçer et al., 2026)'), (421, 'Egypt 2022, EgyptERA'), (450, 'IEA 2025, model value'),
        (550, 'Upper range'), (697, 'Egypt, Dinçer et al. (2026)')]
R['grid_sweep'] = {sc: [dict(ef=ef, label=l, **m1(sc, {'grid_ef': ef})) for ef, l in GRID] for sc in d}

# certificate price x reporting year (rebar certificates, USD M/yr)
FA = {2026: 0.975, 2027: 0.95, 2028: 0.9, 2029: 0.775, 2030: 0.515, 2031: 0.39, 2032: 0.265, 2033: 0.14, 2034: 0.0}
EUR_USD = 85.09 / 75.32
PRICES_EUR = [50, 75.32, 100, 125, 150]
R['price_year'] = {sc: {str(pe): {str(y): m1(sc, {'free_alloc': fa, 'cert_price': pe * EUR_USD})['cert'] / 1e6 for y, fa in FA.items()} for pe in PRICES_EUR} for sc in d}
R['phaseout'] = {sc: {str(y): m1(sc, {'free_alloc': fa}) for y, fa in FA.items()} for sc in d}

# ---------------------------------------------------------------- Monte Carlo (Module 1, global)
rng = np.random.default_rng(42)
N = 3000
draws = dict(grid_ef=rng.triangular(340, 450, 697, N), dr_gas_mult=rng.triangular(0.9, 1.0, 1.1, N),
             reheat_gas_mult=rng.triangular(0.85, 1.0, 1.15, N), ng_carbon=rng.triangular(0.5321, 0.5601, 0.5881, N),
             precursor_mult=rng.triangular(0.7, 1.0, 1.3, N), scrap_c_mult=rng.triangular(0.75, 1.0, 1.5, N),
             alloy_mult=rng.triangular(0.8, 1.0, 1.2, N), bm_mult=rng.triangular(0.95, 1.0, 1.05, N))
mc = {sc: {'chargeable': [], 'footprint': []} for sc in d}
for i in range(N):
    p = {k: float(v[i]) for k, v in draws.items()}
    p['ng_lca_ef'] = 0.32 + 2.053675 * p['ng_carbon'] / 0.5601     # the workbook's link between the two
    for sc in d:
        o = m1(sc, p)
        mc[sc]['chargeable'].append(o['chargeable']); mc[sc]['footprint'].append(o['footprint'])
summ = {}
for sc in d:
    for y in ('chargeable', 'footprint'):
        a = np.array(mc[sc][y])
        summ.setdefault(sc, {})[y] = dict(mean=float(a.mean()), p5=float(np.percentile(a, 5)), p50=float(np.percentile(a, 50)), p95=float(np.percentile(a, 95)))
ch = np.array([mc[s]['chargeable'] for s in ('S2', 'S1', 'Baseline', 'S3')])
fp = np.array([mc[s]['footprint'] for s in ('S2', 'S1', 'Baseline', 'S3')])
rank_ch = float(np.mean(np.all(np.diff(ch, axis=0) > 0, axis=0)))
rank_fp = float(np.mean(np.all(np.diff(fp, axis=0) > 0, axis=0)))
# Spearman rank correlation of each input with baseline rebar chargeable
from scipy.stats import spearmanr
src = {}
for k, v in draws.items():
    src[k] = dict(chargeable=float(spearmanr(v, mc['Baseline']['chargeable'])[0]), footprint=float(spearmanr(v, mc['Baseline']['footprint'])[0]))
R['monte_carlo'] = dict(N=N, summary=summ, ranking_chargeable=rank_ch, ranking_footprint=rank_fp, spearman=src)
print(f'Monte Carlo, {N:,} draws: ranking of the four recipes holds in {100 * rank_ch:.1f}% on the border account and {100 * rank_fp:.1f}% on the footprint', flush=True)

# ---------------------------------------------------------------- B. Module 2 recipe-level OAT
RECIPES = {
    'Baseline': dict(hdri=0, cdri=23.0494287687006, hms1=91.113745467319, hms2=60.7401598294255, gas=5, cdri_row=10, hms1_row=12, hms2_row=15, cao_row=20, mgo_row=32, c_row=42),
    'S1': dict(hdri=0, cdri=0, hms1=101.111111111111, hms2=85.1851851851852, gas=12, hms1_row=11, hms2_row=16, cao_row=20, mgo_row=29, c_row=40),
    'S2': dict(hdri=0, cdri=0, hms1=109.677419354839, hms2=65.1685393258427, gas=11, hms1_row=12, hms2_row=15, cao_row=23, mgo_row=29, c_row=38),
    'Balanced': dict(hdri=0, cdri=0, hms1=110, hms2=71.7647058823529, gas=11, hms1_row=11, hms2_row=14, cao_row=23, mgo_row=29, c_row=38),
    'S3': dict(hdri=23.05, cdri=0, hms1=49.96584, hms2=110.382051764706, gas=12, hms1_row=11, hms2_row=14, cao_row=21, mgo_row=29, c_row=40),
}


def with_param(P, key, mult):
    P = copy.deepcopy(P)
    if key == 'scrap_price':
        for r in range(11, 17): P['pool'][r]['cost'] *= mult
    elif key == 'dri_price':
        for r in range(6, 11): P['pool'][r]['cost'] *= mult
    elif key == 'flux_price':
        for r in list(range(20, 35)) + list(range(38, 47)): P['pool'][r]['cost'] *= mult
    elif key == 'thermal_eff':
        P['E18'] *= mult
    elif key == 'scrap_ef':
        P['B71'] *= mult; P['B72'] *= mult
    elif key == 'dri_ef':
        P['B69'] *= mult; P['B70'] *= mult
    else:
        P[key] *= mult
    return P

M2_PARAMS = [('B60', 'Electricity price'), ('B62', 'Natural-gas price'), ('scrap_price', 'Scrap prices'),
             ('dri_price', 'DRI prices'), ('flux_price', 'Flux and carbon prices'), ('B63', 'Graphite electrode price'),
             ('B61', 'Oxygen price'), ('B82', 'Grid emission factor'), ('E32', 'Auxiliary plant load'),
             ('thermal_eff', 'Furnace thermal efficiency'), ('E31', 'Burner heat-transfer efficiency'),
             ('scrap_ef', 'Scrap emission factors'), ('dri_ef', 'DRI emission factors'), ('B84', 'Oxygen emission factor')]
Bm2 = {}
for rn, rc in RECIPES.items():
    b = evaluate(P0, **rc)
    Bm2[rn] = {'base': dict(cost=float(b['cost']), ghg=float(b['ghg'])), 'params': {}}
    for key, label in M2_PARAMS:
        rec = {'label': label}
        for pct in (-20, -10, 10, 20):
            P = with_param(P0, key, 1 + pct / 100)
            o = evaluate(P, **rc)
            rec[pct] = dict(cost=float(o['cost']), ghg=float(o['ghg']), feasible=bool(o['feasible']))
        rec['S'] = {y: ((rec[10][y] - rec[-10][y]) / Bm2[rn]['base'][y]) / 0.2 for y in ('cost', 'ghg')}
        Bm2[rn]['params'][key] = rec
R['m2_oat'] = Bm2

# ---------------------------------------------------------------- C. Re-optimization under changed conditions
def summarise(b, P):
    pool = P['pool']
    if b is None:
        return None
    return dict(cost=b['cost'], ghg=b['ghg'], gas=b['gas'], hdri=b['hdri'],
                hms1=pool[b['hms1_row']]['name'], hms2=pool[b['hms2_row']]['name'], cao=pool[b['cao_row']]['name'],
                mgo=pool[b['mgo_row']]['name'], carbon=pool[b['c_row']]['name'], hms1_t=b['hms1_t'], hms2_t=b['hms2_t'],
                slag=b['slag'], elec=b['elec'], rows=[b['hms1_row'], b['hms2_row'], b['cao_row'], b['mgo_row'], b['c_row']])

def solve_all(P, label):
    t = time.time()
    out = dict(cost=summarise(optimise(P, 'cost'), P), ghg=summarise(optimise(P, 'ghg'), P),
               hdri=summarise(optimise(P, 'cost', hdri=23.05), P))
    print(label, round(time.time() - t, 1), 's', {k: (round(v['cost']), round(v['ghg'], 2)) if v else None for k, v in out.items()}, flush=True)
    return out

C = {}
C['reference'] = solve_all(P0, 'reference')
P = copy.deepcopy(P0); P['B62'] = 0.285; C['ng_regulated_price'] = solve_all(P, 'ng 0.285')
for ef in (0.10, 0.34, 0.697):
    P = copy.deepcopy(P0); P['B82'] = ef; C[f'grid_{ef}'] = solve_all(P, f'grid {ef}')
for tier in ('Standard Modern', 'Older'):
    C[f'tier_{tier}'] = solve_all(set_tier(P0, tier), f'tier {tier}')
for sl in (0.20, 0.30):
    P = copy.deepcopy(P0); P['B57'] = sl; C[f'slag_{sl}'] = solve_all(P, f'slag {sl}')
for grade in ('Wire Rod (Concrete Mesh)', 'General Steel Structures', 'Hot Rolled Coil (HRC)'):
    P = copy.deepcopy(P0); P['B13'] = grade; C[f'grade_{grade}'] = solve_all(P, f'grade {grade}')
for cap in (0.4, 0.8):
    P = copy.deepcopy(P0)
    for r in (7, 8, 9, 11, 12, 13, 14, 15, 16): P['pool'][r]['N'] = cap * 121000
    C[f'cap_{cap}'] = solve_all(P, f'cap {cap}')
for m in (0.8, 1.2):
    C[f'scrap_price_{m}'] = solve_all(with_param(P0, 'scrap_price', m), f'scrap price {m}')
    C[f'elec_price_{m}'] = solve_all(with_param(P0, 'B60', m), f'elec price {m}')
for aux in (15, 60):
    P = copy.deepcopy(P0); P['E32'] = aux; C[f'aux_{aux}'] = solve_all(P, f'aux {aux}')
R['reopt'] = C

# ---------------------------------------------------------------- D. Internal carbon price (minimize cost + lambda x emissions)
lam_res = []
for lam in (0, 25, 50, 100, 150, 200, 250, 300, 400, 600):
    b = optimise(P0, 'cost', carbon_price=lam)
    best = (b['obj'], b['cost'], b['ghg'], b['hms1_row'], b['hms2_row'], b['cao_row'], b['mgo_row'], b['c_row'], b['gas'])
    pool = P0['pool']
    lam_res.append(dict(lam=lam, cost=best[1], ghg=best[2], hms1=pool[best[3]]['name'], hms2=pool[best[4]]['name'],
                        cao=pool[best[5]]['name'], mgo=pool[best[6]]['name'], carbon=pool[best[7]]['name'], gas=best[8]))
    print('lambda', lam, round(best[1]), round(best[2], 2), flush=True)
R['carbon_price'] = lam_res

# ---------------------------------------------------------------- E. DRI share sweep, coupled to Module 1
sweep = []
for h in (0.0, 5.0, 10.0, 15.0, 20.0, 23.05):
    b = optimise(P0, 'cost', hdri=h, lst_step=0.5)
    rc = dict(hdri=h, cdri=0, hms1=b['hms1_t'], hms2=b['hms2_t'], gas=b['gas'], hms1_row=b['hms1_row'], hms2_row=b['hms2_row'],
              cao_row=b['cao_row'], mgo_row=b['mgo_row'], c_row=b['c_row'])
    sc, o = recipe_to_m1(d['Baseline'], P0, rc)
    r = E.run(sc, base_upstream_ghg=base_up['Baseline'])
    r34 = E.run(sc, {'free_alloc': 0.0}, base_upstream_ghg=base_up['Baseline'])
    heats = float(o['heats'])
    dri_share = (h * P0['pool'][6]['yld']) / 160.0
    sweep.append(dict(hdri=h, dri_lst_share=dri_share, dri_t_yr=h * heats, cost_heat=b['cost'], ghg_heat=b['ghg'],
                      melt_cost_musd=b['cost'] * heats / 1e6, rebar_chargeable=r['hr']['chargeable'], rebar_cert=r['hr']['cert'],
                      rebar_cert_2034=r34['hr']['cert'], rebar_see=r['hr']['see'], billet_chg=r['crude']['chargeable'],
                      footprint_t=r['chain_corrected_t'], recipe=summarise(b, P0)))
    print('hdri', h, round(b['cost']), round(r['hr']['chargeable']), round(r['chain_corrected_t']), flush=True)
R['dri_sweep'] = sweep

# frontier of the reference case (for figure)
pts, front = enumerate_frontier(P0)
R['frontier'] = dict(n_feasible=int(len(pts)), front=front.tolist())

# switching prices: the internal carbon price at which each recipe of the frontier gives way to the next
sw, i = [], 0
while True:
    c0, g0 = front[i]; nxt = None
    for j in range(len(front)):
        if front[j, 1] < g0 - 1e-12:
            lam = (front[j, 0] - c0) / (g0 - front[j, 1])
            if nxt is None or lam < nxt[0] - 1e-12 or (abs(lam - nxt[0]) < 1e-12 and front[j, 1] < front[nxt[1], 1]):
                nxt = (lam, j)
    if nxt is None:
        break
    sw.append(dict(price=float(nxt[0]), cost=float(front[nxt[1], 0]), ghg=float(front[nxt[1], 1]))); i = nxt[1]
R['switching_prices'] = sw
print('switching prices, USD per t CO2e:', [round(x['price'], 1) for x in sw])

# price at which the least-emission recipe pays for itself through certificate savings alone
c_cost, c_ghg = optimise(P0, 'cost'), optimise(P0, 'ghg')
heats = P0['B14'] / P0['F52']
extra = (c_ghg['cost'] - c_cost['cost']) * heats
chg = {sc: E.run(d[sc], base_upstream_ghg=base_up[sc])['hr']['chargeable'] for sc in ('S1', 'S2')}
fpt = {sc: E.run(d[sc], base_upstream_ghg=base_up[sc])['chain_corrected_t'] for sc in ('S1', 'S2')}
R['abatement'] = dict(extra_cost_usd_yr=extra, footprint_abated_t=fpt['S1'] - fpt['S2'], chargeable_abated_t=chg['S1'] - chg['S2'],
                      avg_cost_footprint=extra / (fpt['S1'] - fpt['S2']), border_only_price=extra / (chg['S1'] - chg['S2']))
print('abatement: USD %.2f M a year; %.0f t footprint (USD %.0f per t); %.0f t chargeable (USD %.0f per t)' % (
      extra / 1e6, fpt['S1'] - fpt['S2'], extra / (fpt['S1'] - fpt['S2']), chg['S1'] - chg['S2'], extra / (chg['S1'] - chg['S2'])))
json.dump(R, open(OUT, 'w'), indent=1, default=float)
print('done')
