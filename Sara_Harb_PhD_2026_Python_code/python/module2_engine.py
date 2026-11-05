"""Module 2, EAF Charge Optimization Model: data layer and equation engine.

load_params()  reads every plant parameter, grade limit, emission factor and supplier record from the
               'Admin Setup' and 'Suppliers Pool' tabs of Sara_Harb_PhD_Thesis_Module_2.xlsx, so the
               code and the workbook always share one set of inputs.
evaluate()     computes one heat (or an array of heats) through Equations 1-42 (with 26b, 26c, 34b, 37b
               and 42b), the five feasibility checks, the supplier order ranges (Section 3b), the cost and
               emission register (Section 6b) and the in-furnace process CO2 (Section 6c).

The equations follow the documented equation set (Appendix A of the dissertation).  Variables are named after
the workbook rows that hold the same quantities (C41 = Eq 1, ... C90 = Eq 42), so every value can be compared
with the workbook cell by cell.  The arithmetic is vectorized with numpy, so a whole grid of charge splits and
burner rates is evaluated in one call.
"""
import copy, warnings
import numpy as np
warnings.filterwarnings('ignore')


def load_params(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    A = wb['Admin Setup']; S = wb['Suppliers Pool']
    a = lambda c: A[c].value
    P = {}
    for k in ['B5', 'B8', 'B9', 'B14', 'B35', 'B48', 'B57', 'B60', 'B61', 'B62', 'B63', 'B64', 'B65', 'G65',
              'B69', 'B70', 'B71', 'B72', 'B82', 'B83', 'B84', 'B85', 'B172', 'B173', 'B174',
              'E18', 'E19', 'E20', 'E21', 'E25', 'E26', 'E27', 'E28', 'E29', 'E30', 'E31', 'E32',
              'E42', 'E43', 'E44', 'E45', 'E126', 'E127', 'E132', 'E133', 'E134', 'E135', 'F52', 'F53',
              'C73', 'C74', 'C75', 'C76', 'C77', 'C78', 'C85', 'B13']:
        P[k] = a(k)
    # tier tables (for technology-level sensitivity)
    P['tiers'] = {}
    for col, name in (('B', 'Ultra-Modern'), ('C', 'Standard Modern'), ('D', 'Older')):
        P['tiers'][name] = {r: A[f'{col}{r}'].value for r in (18, 19, 20, 21, 25, 26, 27, 28, 29, 30, 31, 32, 42, 43, 44, 45, 125, 126, 127, 132, 133, 134, 135, 139, 140, 141, 142, 143, 144)}
    P['flux_melt'] = {A[f'G{r}'].value: A[f'E{r}'].value for r in range(139, 145)}
    P['ef_by_name'] = {A[f'B{r}'].value: A[f'C{r}'].value for r in range(109, 121)}
    grades = {}
    for r in range(90, 106):
        grades[A[f'E{r}'].value] = dict(cu=A[f'G{r}'].value, c=A[f'H{r}'].value, b=A[f'I{r}'].value, feo=A[f'J{r}'].value)
    P['grades'] = grades
    # one record per row of 'Suppliers Pool': metallics, CaO and MgO sources, carbon
    pool = {}
    for r in list(range(6, 17)) + list(range(20, 35)) + list(range(38, 47)):
        pool[r] = dict(mat=S[f'A{r}'].value, name=S[f'B{r}'].value,
                       cost=S[f'C{r}'].value, yld=S[f'D{r}'].value,
                       c=S[f'E{r}'].value, met=S[f'F{r}'].value, cu=S[f'G{r}'].value,
                       fe=S[f'H{r}'].value, si=S[f'I{r}'].value, h2o=S[f'J{r}'].value,
                       M=S[f'M{r}'].value, N=S[f'N{r}'].value, O=S[f'O{r}'].value)
    P['pool'] = pool
    return P


CALC_LIST = ["Burnt Lime (CaO)", "Local Limestone (CaCO3)", "Dolomite CaMg(CO3)2", "Magnesite (MgCO3)", "Synthetic MgO"]


def set_tier(P, tier):
    """Apply a technology tier (as Admin Setup column B/C/D) to the → USED cells."""
    P = copy.deepcopy(P)
    t = P['tiers'][tier]
    for r in (18, 19, 20, 21, 25, 26, 27, 28, 29, 30, 31, 32, 42, 43, 44, 45, 126, 127, 132, 133, 134, 135):
        P[f'E{r}'] = t[r]
    P['flux_melt'] = dict(zip(["Burnt Lime (CaO)", "Local Limestone (CaCO3)", "Dolomite CaMg(CO3)2", "Magnesite (MgCO3)", "Synthetic MgO", "Carbon (all types)"],
                              [t[r] for r in range(139, 145)]))
    return P


def evaluate(P, hdri, cdri, hms1, hms2, gas, cdri_row=7, hms1_row=11, hms2_row=14, cao_row=20, mgo_row=26, c_row=38,
             grade=None, detail=False):
    pool = P['pool']
    g = P['grades'][grade or P['B13']]
    C7, C8, C9, C10 = g['cu'], g['c'], g['b'], g['feo']
    C12 = P['F52']; C14 = P['B14'] / C12
    m = [pool[6], pool[cdri_row], pool[hms1_row], pool[hms2_row]]
    K = [P['E132'], P['E133'], P['E134'], P['E135']]
    W = [np.asarray(hdri, float), np.asarray(cdri, float), np.asarray(hms1, float), np.asarray(hms2, float)]
    gas = np.asarray(gas, float)
    ca, mg, cs = pool[cao_row], pool[mgo_row], pool[c_row]
    ca_mat = ca['name'].split(' — ')[0]; mg_mat = mg['name'].split(' — ')[0]; c_mat = cs['name'].split(' — ')[0]
    # Eq 1  liquid-steel yield (t)
    C41 = sum(w * x['yld'] for w, x in zip(W, m))
    # Eq 2  yield variance (t), Check 1 requires >= 0
    C42 = C41 - C12
    # Eq 3  tramp copper (kg), summed over all four metallics
    C43 = sum(w * 1000 * x['cu'] for w, x in zip(W, m))
    # Eq 4  final copper concentration (fraction of liquid steel), Check 2
    C44 = C43 / (C41 * 1000)
    C45 = W[0] * 1000 * m[0]['fe'] * (1 - m[0]['met']) * 1.286 + W[1] * 1000 * m[1]['fe'] * (1 - m[1]['met']) * 1.286
    C46 = C45 * P['B35']
    C47 = sum(w * 1000 * x['c'] for w, x in zip(W, m))
    C48 = C45 * 0.167
    C49 = C47 - C48
    C50 = sum(w * 1000 * x['si'] for w, x in zip(W, m))
    C51 = C50 * C9
    C52 = C50 + C45 + C51
    C53 = C52 / (1 - P['E29'])
    C54 = C53 * P['E29']
    C55 = (C41 * 1000) * C8
    C56 = np.maximum(C53 * (P['E30'] - C10) * 0.167, 0)
    C57 = C55 + C56
    C58 = np.maximum(C57 - C49, 0)
    C59 = C51 / (ca['yld'] * ca['M'])
    C60 = C54 / (mg['yld'] * mg['M'])
    C61 = np.where(C58 > 0, C58 / (cs['yld'] * cs['M']), 0)
    K26 = P['flux_melt'][ca_mat]; K27 = P['flux_melt'][mg_mat]
    C62 = sum(w * k for w, k in zip(W, K)) + (C59 / 1000 * K26) + (C60 / 1000 * K27)
    C63 = sum(w * x['h2o'] * P['E28'] for w, x in zip(W, m)) + (C59 / 1000 * ca['si'] * P['E28']) + (C60 / 1000 * mg['si'] * P['E28'])
    C65 = C59 / ca['yld']; C66 = C60 / mg['yld']
    C67 = C65 + C66 + C53
    C68 = (C58 * (1 - cs['si'])) * P['E25']
    C69 = C41 * gas
    C70 = C69 * P['B64'] * P['E31']
    C71 = (C62 + C63 + C46) - C68 - (C70 if P['B65'] == 'Yes' else 0)
    C72 = P['B8'] - P['B9']
    C73 = (C41 + C67 / 1000) * P['E27'] * C72
    C74 = P['E20'] * 1000 * P['E19'] * P['E18']
    C75 = C71 + C73
    C76 = (C75 / P['F53']) * 60
    C82 = ((W[0] + W[1]) * 1000) / P['E21']
    C83 = np.maximum(C76, C82)
    C77 = (P['E26'] * C83 / 60) / C75 if P['G65'] == 'Energy-based' else (P['E26'] * C83) / C74
    C78 = C77 * C75
    C79 = C75 + C78
    C80 = C41 * P['E32']
    C81 = C79 + C80
    C84 = (C79 / 1000) * P['E42']
    C85 = C83 * P['E43']
    C86 = C84 + C85
    C87 = C86 / C41
    C88 = np.where(C57 < C49, (C49 - C57) * P['E44'], 0)
    C89 = np.maximum(C88 + C69 * P['E45'], P['B174'] * C41 if P['B173'] == 'Yes' else 0)
    C90 = P['E127'] - P['E126']
    slag = (C67 / 1000) / C41
    chk = dict(chk1=C42 >= -1e-6, chk2=C44 <= C7, chk3=slag <= P['B57'], chk4=C83 <= C90, chk5=C87 <= P['B48'])
    feasible = chk['chk1'] & chk['chk2'] & chk['chk3'] & chk['chk4'] & chk['chk5']
    # cost register (Section 6b)
    efn = P['ef_by_name']
    cost_items = dict(
        hdri=W[0] * pool[6]['cost'], cdri=W[1] * m[1]['cost'], hms1=W[2] * m[2]['cost'], hms2=W[3] * m[3]['cost'],
        cao=(C59 / 1000) * ca['cost'], mgo=(C60 / 1000) * mg['cost'], carbon=(C61 / 1000) * cs['cost'],
        elec=C81 * (P['B60'] / P['B5']), o2=C89 * P['B61'], ng=C69 * P['B62'], graphite=C86 * P['B63'])
    ef_items = dict(
        hdri=W[0] * P['B69'], cdri=W[1] * P['B70'], hms1=W[2] * P['B71'], hms2=W[3] * P['B72'],
        cao=(C59 / 1000) * efn[ca['mat']], mgo=(C60 / 1000) * efn[mg['mat']], carbon=(C61 / 1000) * efn[cs['mat']],
        elec=C81 / 1000 * P['B82'], o2=C89 * P['B84'], ng=C69 * P['B83'], graphite=C86 * P['B85'])
    calc = {n: P[c] for n, c in zip(CALC_LIST, ['C73', 'C74', 'C75', 'C76', 'C77'])}
    proc = dict(cao=(C59 / 1000) * calc[ca_mat] * ca['yld'], mgo=(C60 / 1000) * calc[mg_mat] * mg['yld'],
                carbon=(C61 / 1000) * P['C78'] * cs['yld'], graphite=(C86 / 1000) * P['C85'])
    cost = sum(cost_items.values())
    ghg = sum(ef_items.values()) + sum(proc.values())
    # supplier order ranges (Section 3b)
    def inrange(annual, lo, hi):
        return (annual < 0.01) | ((annual >= lo) & (annual <= hi))
    order_ok = (inrange(W[1] * C14, m[1]['M'], m[1]['N']) & inrange(W[2] * C14, m[2]['M'], m[2]['N']) &
                inrange(W[3] * C14, m[3]['M'], m[3]['N']) & inrange(C59 / 1000 * C14, ca['N'], ca['O']) &
                inrange(C60 / 1000 * C14, mg['N'], mg['O']) & inrange(C61 / 1000 * C14, cs['N'], cs['O']) &
                ((W[0] * C14) <= pool[6]['N'] + 1e-6))
    out = dict(cost=cost, ghg=ghg, feasible=feasible & order_ok, chk_ok=feasible, order_ok=order_ok, slag=slag,
               cu=C44, pon=C83, wear=C87, elec_kwh=C81, lst=C41, heats=C14)
    if detail:
        out.update(dict(cost_items=cost_items, ef_items=ef_items, proc=proc, C59=C59, C60=C60, C61=C61, C89=C89,
                        C86=C86, C69=C69, arc=C79, aux=C80))
    return out
