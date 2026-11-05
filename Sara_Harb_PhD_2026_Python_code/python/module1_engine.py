"""Module 1, stage-level emissions, CBAM attribution and cost: independent re-implementation of the calculation chain
(GHG footprint, CBAM direct / indirect / precursor attribution, specific embedded emissions,
cumulative benchmark, chargeable emissions and certificate cost) from the row ledger of the
workbook's stage tables.  Row-level quantities are recomputed from activity data and factors so
that any factor or quantity can be perturbed for sensitivity analysis."""
import copy

STAGES = ['Pelletizing', 'DRP', 'EAF', 'Secondary Metallurgy', 'Continuous Casting', 'Rolling Mill', 'Fabrication']
INPUT_TABLES = {
    'Pelletizing': ['BL_Pellet_input'],
    'DRP': ['BL_DRI_reactor', 'CDRI_Input_table', 'HBI_input_table', 'HTS_input_table'],
    'EAF': ['EAF_Input_table'], 'Secondary Metallurgy': ['SM_input_table'], 'Continuous Casting': ['CC_input_table'],
    'Rolling Mill': ['HRM_input_table'], 'Fabrication': ['FAB_input_table']}
STEP_BM = {'pellet': 0.086, 'dr': 0.295, 'crude': 0.065, 'hr': 0.038, 'fab': 0.112}
K = 44 / 12

BASE = dict(grid_ef=450.0, ng_lca_ef=2.373675, ng_comb_mult=1.0, ng_carbon=0.5601, cert_price=85.09, free_alloc=0.975,
            precursor_mult=1.0, dr_gas_mult=1.0, reheat_gas_mult=1.0, bm_mult=1.0, scrap_c_mult=1.0,
            alloy_mult=1.0, origin_deduction=0.0)


def num(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


def table_rows(sc, stage, key):
    t = sc[stage].get(key)
    if t is None:
        for k in sc[stage]:
            if k.startswith(key + '_S'):
                t = sc[stage][k]; break
    return t['rows'] if t else []


def is_ng(r):
    return r.get('Unit') in ('m³',) and abs(num(r.get('Carbon Content (kg C per Unit)')) - 0.5601) < 1e-6


def is_elec(r):
    return r.get('Specific Type') == 'Grid Electricity'


def is_dri(r):
    t = str(r.get('Specific Type') or '')
    return r.get('Input Category') == 'Metallic Feedstock' and ('DRI' in t) and 'Metallic DRI' not in t


def row_calc(r, p, stage, upstream=None):
    """Return recomputed row quantities."""
    ad0 = num(r.get('Activity Data')); ad = ad0
    if is_ng(r) and stage == 'DRP':
        ad = ad0 * p['dr_gas_mult']
    if is_ng(r) and stage == 'Rolling Mill':
        ad = ad0 * p['reheat_gas_mult']
    ef0 = num(r.get('EF (kg CO₂e per Unit)'))
    ef = ef0
    if is_elec(r):
        ef = p['grid_ef']
    elif is_ng(r):
        ef = p['ng_lca_ef']
    elif is_dri(r) and stage == 'EAF' and upstream is not None:
        ef = ef0 * upstream['dri_ef_ratio']
    if r.get('Input Category') == 'Additives' and stage in ('EAF', 'Secondary Metallurgy') and any(
            k in str(r.get('Specific Type')) for k in ('Ferro', 'Silicon', 'Aluminum')):
        ef = ef0 * p['alloy_mult']
    ghg = ad * ef
    cc = num(r.get('Carbon Content (kg C per Unit)'))
    if is_ng(r):
        cc = p['ng_carbon']
    if r.get('Input Category') == 'Metallic Feedstock' and 'Scrap' in str(r.get('Specific Type')) or 'HMS' in str(r.get('Specific Type')):
        cc = cc * p['scrap_c_mult']
    internal = r.get('Internal Transfer Within This Process?') == 'Yes'
    cin = 0.0 if internal or r.get('Carbon In (kg C)') in (None, '') else ad * cc
    dirf0 = num(r.get('CBAM Direct Emissions from Fuel (t CO₂)'))
    dirf = dirf0 * (ad / ad0 if ad0 else 0) * p['ng_comb_mult'] * (cc / 0.5601 if is_ng(r) else 1)
    proc = 0.0 if internal or r.get('CBAM Process Emissions from Carbon Inputs (t CO₂)') in (None, '') else cin * K / 1000
    ind = (ad * p['grid_ef'] / 1000) if (is_elec(r) and r.get('CBAM Indirect Emissions from Electricity (t CO₂)') not in (None, '')) else 0.0
    emb = num(r.get('CBAM Embedded Emissions (t CO₂e)')) * (ad / ad0 if ad0 else 0) * p['precursor_mult']
    bmp = num(r.get('Benchmark of purchased precursors (t CO₂e)')) * (ad / ad0 if ad0 else 0) * p['bm_mult']
    return dict(ad=ad, ghg=ghg, cin=cin, dirf=dirf, proc=proc, ind=ind, emb=max(emb, 0), bmp=bmp,
                is_up=num(r.get('CBAM Internal Precursor Emissions (t CO₂)')) > 0 or num(r.get('Benchmark from an earlier process (t CO₂e)')) > 0,
                cost=num(r.get('Material Cost (USD)')) * (ad / ad0 if ad0 else 0))


def primary(sc, stage, tables):
    tot = 0.0
    for t in tables:
        for r in table_rows(sc, stage, t):
            if r.get('Output Category') == 'Primary Product':
                tot += num(r.get('Activity Data'))
    return tot


def cout(sc, stage, tables):
    return sum(num(r.get('Carbon Out (kg C)')) for t in tables for r in table_rows(sc, stage, t))


def run(sc, p=None, base_upstream_ghg=None):
    p = dict(BASE, **(p or {}))
    res = {}
    bm = {k: v * p['bm_mult'] for k, v in STEP_BM.items()}
    FA = p['free_alloc']

    def proc_block(name, stages, up_see, up_bm, method, step_bm, prod, c_out=None, indirect=False, upstream=None):
        rows = []
        for st in stages:
            for t in INPUT_TABLES[st]:
                for r in table_rows(sc, st, t):
                    rc = row_calc(r, p, st, upstream)
                    rows.append((r, rc))
        ghg = sum(rc['ghg'] for _, rc in rows)
        cin = sum(rc['cin'] for _, rc in rows)
        if method == 'mb' and cin > 0:
            direct = (cin - c_out) * K / 1000
        else:
            direct = sum(rc['dirf'] + rc['proc'] for _, rc in rows)
        ind = sum(rc['ind'] for _, rc in rows) if indirect else 0.0
        emb = sum(rc['emb'] for _, rc in rows)
        up_ad = sum(rc['ad'] for r, rc in rows if rc['is_up'])
        internal = up_ad * up_see
        bme = up_ad * up_bm
        bmp = sum(rc['bmp'] for _, rc in rows)
        attributed = direct + ind + emb + internal
        see = attributed / prod if prod else 0.0
        cum = (step_bm + (bme + bmp) / prod) if prod else step_bm
        charge_t = max(0.0, see - cum * FA - p['origin_deduction']) if prod else 0.0
        out = dict(ghg_kg=ghg, prod=prod, direct=direct, indirect=ind, precursor_bought=emb, internal=internal,
                   attributed=attributed, see=see, cum_bm=cum, charge_per_t=charge_t, chargeable=charge_t * prod,
                   cert=charge_t * prod * p['cert_price'], cost=sum(rc['cost'] for _, rc in rows),
                   stage_ghg={st: sum(rc['ghg'] for r, rc in rows if True) for st in []})
        # per-stage GHG
        for st in stages:
            out.setdefault('by_stage', {})[st] = sum(row_calc(r, p, st, upstream)['ghg'] for t in INPUT_TABLES[st] for r in table_rows(sc, st, t))
        return out

    pel = proc_block('pellet', ['Pelletizing'], 0, 0, 'cf', bm['pellet'], primary(sc, 'Pelletizing', ['BL_Pellet_Output']), indirect=True)
    dr_prod = primary(sc, 'DRP', ['CDRI_output_table', 'HBI_output_table', 'HTS_output_table'])
    dr = proc_block('dr', ['DRP'], pel['see'], pel['cum_bm'], 'mb', bm['dr'], dr_prod,
                    c_out=cout(sc, 'DRP', ['CDRI_output_table', 'HBI_output_table', 'HTS_output_table']))
    up_ghg = pel['ghg_kg'] + dr['ghg_kg']
    ratio = (up_ghg / base_upstream_ghg) if (base_upstream_ghg and up_ghg) else 1.0
    upstream = dict(dri_ef_ratio=ratio)
    crude = proc_block('crude', ['EAF', 'Secondary Metallurgy', 'Continuous Casting'], dr['see'], dr['cum_bm'], 'mb', bm['crude'],
                       primary(sc, 'Continuous Casting', ['CC_Output_table']), c_out=cout(sc, 'Continuous Casting', ['CC_Output_table']),
                       upstream=upstream)
    hr = proc_block('hr', ['Rolling Mill'], crude['see'], crude['cum_bm'], 'cf', bm['hr'], primary(sc, 'Rolling Mill', ['HRM_output_table']))
    fab = proc_block('fab', ['Fabrication'], hr['see'], hr['cum_bm'], 'cf', bm['fab'], primary(sc, 'Fabrication', ['FABo_output_table']))
    res = dict(pellet=pel, dr=dr, crude=crude, hr=hr, fab=fab)
    stage_ghg = {}
    for blk in res.values():
        stage_ghg.update(blk['by_stage'])
    res['stage_ghg_t'] = {k: v / 1000 for k, v in stage_ghg.items()}
    # whole-chain footprint without double counting: DRI line in the EAF carries the own-chain upstream
    dri_line = sum(row_calc(r, p, 'EAF', upstream)['ghg'] for r in table_rows(sc, 'EAF', 'EAF_Input_table') if is_dri(r)) / 1000
    res['dri_line_t'] = dri_line
    res['chain_sum_t'] = sum(res['stage_ghg_t'].values())
    res['chain_corrected_t'] = res['chain_sum_t'] - dri_line if (pel['prod'] > 0 or dr['prod'] > 0) else res['chain_sum_t']
    res['upstream_ghg_kg'] = up_ghg
    return res
