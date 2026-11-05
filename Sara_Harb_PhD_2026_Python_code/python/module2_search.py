"""Module 2, EAF Charge Optimization Model: exhaustive search.

The discrete layer is the supplier choice.  Its options are the rows of the 'Suppliers Pool' tab:

    CDRI 4  x  HMS1 3  x  HMS2 3  x  CaO source 6  x  MgO source 9  x  carbon source 9  =  17,496 combinations

HDRI has a single on-site source, so it carries no selector.  For every combination the continuous layer is
scanned in full: the liquid-steel target is split between the two scrap streams in steps of `lst_step` t of
liquid steel (161 steps of 1 t for the 160 t target), each stream's charge following from its yield, and
the burner rate is swept from 0 to 12 Nm3 per tonne of liquid steel.  HDRI and CDRI enter at the tonnages
given (`hdri`, `cdri_grid`); the default leaves CDRI at zero, and `cdri_grid` widens the search so that DRI
can also enter from any of the four CDRI sources.

Every heat is passed through module2_engine.evaluate(); a heat that fails one of the five checks, or places
an annual order outside a supplier's minimum and maximum, is discarded.  A material at effectively zero use
is exempt from its order range.  Nothing is sampled, so the optimum returned is global for the model as
parameterized and for the step chosen.
"""
import itertools
import numpy as np
from module2_engine import evaluate

SEARCH_SPACE = dict(cdri=range(7, 11), hms1=range(11, 14), hms2=range(14, 17),
                    cao=range(20, 26), mgo=range(26, 35), c=range(38, 47))     # rows of 'Suppliers Pool'
ROWS = SEARCH_SPACE                                                             # alias used by older scripts


def n_combinations():
    n = 1
    for r in SEARCH_SPACE.values():
        n *= len(r)
    return n                                                                    # 17,496


def _grid(rem, lst_step):
    ks = np.arange(0, rem + 1e-9, lst_step)
    if ks[-1] < rem - 1e-9:
        ks = np.append(ks, rem)
    return ks


def _combos(cdri_rows):
    return itertools.product(cdri_rows, SEARCH_SPACE['hms1'], SEARCH_SPACE['hms2'],
                             SEARCH_SPACE['cao'], SEARCH_SPACE['mgo'], SEARCH_SPACE['c'])


def optimize(P, objective='cost', hdri=0.0, lst_step=1.0, gas_vals=range(0, 13), cost_cap=None,
             cdri_grid=(0.0,), cdri_rows=None, cdri_t=None, cdri_row=None, carbon_price=None, hms_cap_share=None):
    """Best feasible recipe for objective 'cost' (USD a heat) or 'ghg' (t CO2e a heat).

    hdri      fixed hot-DRI charge (t a heat); 23.05 t reproduces the HDRI-floor tab.
    cost_cap  upper bound on cost (USD a heat); with objective 'ghg' this is the Balanced tab.
    cdri_grid CDRI tonnages (t a heat) to try for every CDRI source; (0,) leaves CDRI out of the charge.
    cdri_t / cdri_row  fix one CDRI tonnage and source (kept for the scripts of Chapters 6 and 7).
    carbon_price  USD per t CO2e; minimizes cost + carbon_price x emissions (the internal carbon price).
    """
    pool = P['pool']
    if cdri_t is not None:
        cdri_grid = (float(cdri_t),)
    if cdri_rows is None:
        if cdri_row is not None:
            cdri_rows = (cdri_row,)
        elif all(t == 0 for t in cdri_grid):
            cdri_rows = (SEARCH_SPACE['cdri'][0],)   # no CDRI charged: the four sources give identical heats
        else:
            cdri_rows = SEARCH_SPACE['cdri']
    gas = np.array(list(gas_vals), float)
    best = None
    for rd in cdri_rows:
        for cdri in cdri_grid:
            rem = P['F52'] - hdri * pool[6]['yld'] - cdri * pool[rd]['yld']
            if rem < -1e-9:
                continue
            KK, GG = np.meshgrid(_grid(rem, lst_step), gas, indexing='ij')
            for _, r1, r2, rc, rm, rcar in _combos((rd,)):
                w1 = KK / pool[r1]['yld']                  # HMS1 charge (t)
                w2 = (rem - KK) / pool[r2]['yld']          # HMS2 charge (t)
                o = evaluate(P, hdri, cdri, w1, w2, GG, cdri_row=rd, hms1_row=r1,
                             hms2_row=r2, cao_row=rc, mgo_row=rm, c_row=rcar)
                ok = o['feasible']                         # five checks and order ranges
                if cost_cap is not None:
                    ok = ok & (o['cost'] <= cost_cap)
                if not ok.any():
                    continue
                if carbon_price is not None:
                    score = o['cost'] + carbon_price * o['ghg']
                else:
                    score = o[objective]
                val = np.where(ok, score, np.inf)
                i = np.unravel_index(np.argmin(val), val.shape)
                if best is None or val[i] < best['obj'] - 1e-9:
                    best = dict(obj=float(val[i]), cost=float(o['cost'][i]),
                                ghg=float(o['ghg'][i]), hdri=float(hdri), cdri_t=float(cdri),
                                cdri_row=rd, hms1_row=r1, hms2_row=r2, cao_row=rc,
                                mgo_row=rm, c_row=rcar, hms1_t=float(w1[i]),
                                hms2_t=float(w2[i]), gas=float(GG[i]),
                                elec=float(o['elec_kwh'][i]), slag=float(o['slag'][i]))
    if best is not None:
        if best['cdri_t'] == 0:
            best['cdri_row'] = SEARCH_SPACE['cdri'][0]       # source is immaterial when no CDRI is charged
        best['names'] = {k: pool[best[k + '_row']]['name'] for k in ('cdri', 'hms1', 'hms2', 'cao', 'mgo', 'c')}
    return best


optimise = optimize                                     # alias used by older scripts


def enumerate_frontier(P, hdri=0.0, lst_step=1.0, gas_vals=range(0, 13)):
    """Every distinct feasible (cost, ghg) recipe and its non-dominated subset (the Pareto frontier).
    With no CDRI charged, the four CDRI sources give identical heats, so the scan runs over the
    4,374 combinations of the other five selectors and counts each distinct recipe once."""
    pool = P['pool']
    rem = P['F52'] - hdri * pool[6]['yld']
    KK, GG = np.meshgrid(_grid(rem, lst_step), np.array(list(gas_vals), float), indexing='ij')
    pts = []
    for _, r1, r2, rc, rm, rcar in _combos((SEARCH_SPACE['cdri'][0],)):
        w1 = KK / pool[r1]['yld']; w2 = (rem - KK) / pool[r2]['yld']
        o = evaluate(P, hdri, 0, w1, w2, GG, hms1_row=r1, hms2_row=r2, cao_row=rc, mgo_row=rm, c_row=rcar)
        ok = o['feasible']
        if ok.any():
            pts.append(np.stack([o['cost'][ok], o['ghg'][ok]], 1))
    pts = np.concatenate(pts)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]
    front, best_g = [], np.inf
    for c, g in pts:
        if g < best_g - 1e-9:
            front.append((c, g)); best_g = g
    return pts, np.array(front)


def optimize_with_dri(P, objective='cost', hdri_step=1.0, cdri_step=2.0, cdri_max=60.0, lst_step=1.0,
                      gas_vals=(11, 12), cost_cap=None, refine=0.02, keep=5):
    """Search in which DRI is free to enter the charge: hot DRI from the own plant (up to its output) and cooled
    DRI from any of the four CDRI sources, together with the 17,496 supplier combinations.

    The coarse layer scans HDRI in `hdri_step` t, CDRI in `cdri_step` t up to `cdri_max` and the scrap split in
    `lst_step` t of liquid steel; the `keep` best combinations are then refined to `refine` t around their optimum
    in all three tonnages, so that a recipe can sit exactly on a supplier's order limit.  Burner rates below
    11 Nm3/t raise both cost and emissions in the reference case, so 11 and 12 are scanned by default."""
    pool = P['pool']
    heats = P['B14'] / P['F52']
    hmax = pool[6]['N'] / heats
    hvals = np.unique(np.append(np.arange(0, hmax, hdri_step), hmax))
    cvals = np.arange(0, cdri_max + 1e-9, cdri_step)
    gas = np.array(list(gas_vals), float)

    def scan(h_arr, c_arr, k_arr, rd, r1, r2, rc, rm, rcar):
        KK, GG, CC = np.meshgrid(k_arr, gas, c_arr, indexing='ij')
        rem = P['F52'] - h_arr * pool[6]['yld'] - CC * pool[rd]['yld']
        valid = (KK >= -1e-9) & (KK <= rem + 1e-9) & (CC >= 0)
        w1 = KK / pool[r1]['yld']
        w2 = np.maximum(rem - KK, 0) / pool[r2]['yld']
        o = evaluate(P, h_arr, CC, w1, w2, GG, cdri_row=rd, hms1_row=r1, hms2_row=r2,
                     cao_row=rc, mgo_row=rm, c_row=rcar)
        ok = o['feasible'] & valid
        if cost_cap is not None:
            ok = ok & (o['cost'] <= cost_cap)
        if not ok.any():
            return None
        val = np.where(ok, o[objective], np.inf)
        i = np.unravel_index(np.argmin(val), val.shape)
        return dict(obj=float(val[i]), cost=float(o['cost'][i]), ghg=float(o['ghg'][i]), hdri=float(h_arr),
                    cdri_t=float(CC[i]), cdri_row=rd, hms1_row=r1, hms2_row=r2, cao_row=rc, mgo_row=rm,
                    c_row=rcar, hms1_t=float(w1[i]), hms2_t=float(w2[i]), gas=float(GG[i]), lst_k=float(KK[i]))

    tops = []
    for h in hvals:
        kmax = P['F52'] - h * pool[6]['yld']
        k_arr = np.arange(0, kmax + 1e-9, lst_step)
        for combo in _combos(SEARCH_SPACE['cdri']):
            b = scan(h, cvals, k_arr, *combo)
            if b is not None:
                tops.append(b)
    tops.sort(key=lambda b: b['obj'])
    seen, cands = set(), []
    for b in tops:
        key = tuple(b[k] for k in ('cdri_row', 'hms1_row', 'hms2_row', 'cao_row', 'mgo_row', 'c_row'))
        if key not in seen:
            seen.add(key); cands.append(b)
        if len(cands) == keep:
            break
    best = cands[0] if cands else None
    for b in cands:                                   # refinement around each of the best combinations
        combo = (b['cdri_row'], b['hms1_row'], b['hms2_row'], b['cao_row'], b['mgo_row'], b['c_row'])
        h_fine = np.unique(np.clip(np.append(np.arange(b['hdri'] - hdri_step, b['hdri'] + hdri_step + 1e-9, refine), hmax), 0, hmax))
        c_fine = np.arange(max(b['cdri_t'] - cdri_step, 0), b['cdri_t'] + cdri_step + 1e-9, refine)
        k_fine = np.arange(max(b['lst_k'] - 2 * lst_step, 0), b['lst_k'] + 2 * lst_step + 1e-9, refine)
        for h in h_fine:
            r = scan(h, c_fine, k_fine, *combo)
            if r is not None and r['obj'] < best['obj'] - 1e-9:
                best = r
    if best is not None:
        best['names'] = {k: pool[best[k + '_row']]['name'] for k in ('cdri', 'hms1', 'hms2', 'cao', 'mgo', 'c')}
    return best
