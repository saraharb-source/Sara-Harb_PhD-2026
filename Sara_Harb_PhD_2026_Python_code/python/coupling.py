"""Shared-register transfer: annualize a Module 2 recipe and write it into a copy of the Module 1
baseline scenario set (EAF input table; pelletizing and DR stages scaled to the DRI actually charged)."""
import copy
import module1_engine as E
from module2_engine import evaluate

SCALE_FIELDS_IN = ['Activity Data', 'CBAM Direct Emissions from Fuel (t CO₂)', 'CBAM Embedded Emissions (t CO₂e)',
                   'Benchmark of purchased precursors (t CO₂e)', 'CBAM Indirect Emissions from Electricity (t CO₂)',
                   'Material Cost (USD)', 'GHG Emissions (kg CO₂e)', 'Carbon In (kg C)']
SCALE_FIELDS_OUT = ['Activity Data', 'Carbon Out (kg C)']


def scale_stage(sc, stage, f):
    for tname, t in sc[stage].items():
        for r in t['rows']:
            for k in (SCALE_FIELDS_OUT if 'utput' in tname else SCALE_FIELDS_IN):
                if isinstance(r.get(k), (int, float)):
                    r[k] = r[k] * f


def mkrow(cat, typ, ad, unit, ef, cc=None, dirf=None, up=False, extra=None):
    r = {'Input Category': cat, 'Specific Type': typ, 'Activity Data': ad, 'Unit': unit, 'EF (kg CO₂e per Unit)': ef,
         'Internal Transfer Within This Process?': 'No'}
    if cc is not None:
        r['Carbon Content (kg C per Unit)'] = cc
        r['Carbon In (kg C)'] = ad * cc
        r['CBAM Process Emissions from Carbon Inputs (t CO₂)'] = ad * cc * 44 / 12 / 1000
    if dirf is not None:
        r['CBAM Direct Emissions from Fuel (t CO₂)'] = dirf
    if up:
        r['CBAM Internal Precursor Emissions (t CO₂)'] = 1.0
        r['Benchmark from an earlier process (t CO₂e)'] = 1.0
    if extra:
        r.update(extra)
    return r


FLUX_C = {'Burnt Lime (CaO)': 0.0, 'Local Limestone (CaCO3)': 0.12, 'Dolomite CaMg(CO3)2': 0.1303, 'Magnesite (MgCO3)': 0.1425, 'Synthetic MgO': 0.0}


def recipe_to_m1(base_sc, P, recipe, base_dri_t=15154.5551, hdri_hot=True):
    """recipe: dict(hdri, cdri, hms1, hms2, gas, *_row) per heat."""
    o = evaluate(P, detail=True, **recipe)
    H = float(o['heats'])
    pool = P['pool']
    sc = copy.deepcopy(base_sc)
    eaf_key = [k for k in sc['EAF'] if k.startswith('EAF_Input')][0]
    old = sc['EAF'][eaf_key]['rows']
    keep = [r for r in old if any(s in str(r.get('Specific Type')) for s in ('Ferrosilicon', 'Ferromanganese', 'MgO-C'))]
    rows = []
    dri_t = (recipe.get('hdri', 0) + recipe.get('cdri', 0)) * H
    if dri_t > 0:
        ef = P['B69'] * 1000 if recipe.get('hdri', 0) > 0 else P['B70'] * 1000
        rows.append(mkrow('Metallic Feedstock', 'Hot DRI (HDRI)' if recipe.get('hdri', 0) > 0 else 'Cold DRI (from the DR plant)',
                          dri_t, 'tons', ef, cc=22, up=True))
    for key, rr in (('hms1', recipe['hms1_row']), ('hms2', recipe['hms2_row'])):
        ad = recipe[key] * H
        rows.append(mkrow('Metallic Feedstock', f"{pool[rr]['name']} Scrap {key.upper()}", ad, 'tons',
                          P['B71'] * 1000 if key == 'hms1' else P['B72'] * 1000, cc=pool[rr]['c'] * 1000))
    ca = pool[recipe['cao_row']]; mg = pool[recipe['mgo_row']]; cs = pool[recipe['c_row']]
    efn = P['ef_by_name']
    for q, mat in ((o['C59'], ca), (o['C60'], mg)):
        name = mat['name'].split(' — ')[0]
        rows.append(mkrow('Silo Flux', name, float(q) * H, 'kg', efn[mat['mat']], cc=FLUX_C[name]))
    rows.append(mkrow('Carbon Source', cs['name'], float(o['C61']) * H, 'kg', efn[cs['mat']], cc=cs['yld']))
    rows += [copy.deepcopy(r) for r in keep]
    rows.append(mkrow('Utilities', 'Industrial O₂', float(o['C89']) * H, 'Nm³', P['B84'] * 1000, cc=None))
    ng = float(o['C69']) * H
    rows.append(mkrow('Utilities', 'Burner Fuel', ng, 'm³', P['B83'] * 1000, cc=0.5601, dirf=ng * 0.0020537033))
    rows[-1].pop('CBAM Process Emissions from Carbon Inputs (t CO₂)', None)
    rows.append(mkrow('Utilities', 'Grid Electricity', float(o['elec_kwh']) * H / 1000, 'MWh', P['B82'] * 1000))
    rows.append(mkrow('Consumables', 'UHP Grade', float(o['C86']) * H, 'kg', P['B85'] * 1000, cc=0.99))
    sc['EAF'][eaf_key]['rows'] = rows
    # upstream stages follow the DRI actually charged
    f = dri_t / base_dri_t
    for st in ('Pelletizing', 'DRP'):
        scale_stage(sc, st, f)
    if dri_t > 0 and hdri_hot:
        pass  # hot vs cold only changes the DRI-line factor; DR stage kept on the baseline cooled configuration
    return sc, o
