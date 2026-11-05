"""Chapter 7 validation runs: cradle-to-gate footprint per tonne of rebar at two grid factors (450 and 706 g CO2e
per kWh), and the reconfiguration of the reference plant to a DRI-dominant route (57% of liquid steel from its
own cooled DRI, 43% imported scrap) for the comparison with the CARES EPD 0038 product.
Usage: python validation_chapter7.py [--m1 <file>] [--m2 <file>]"""
import json
import paths
import module1_engine as E
from module2_engine import load_params, evaluate
from coupling import recipe_to_m1
d = paths.module1_rows(); P = load_params(paths.M2)
base_up = {sc: E.run(d[sc])['upstream_ghg_kg'] for sc in d}
out = {}
# model cradle-to-gate (A1+A3) per t rebar, corrected for the DRI double count, at three grid factors
for sc in d:
    out[sc] = {}
    for ef in (450, 706):
        r = E.run(d[sc], {'grid_ef': ef}, base_upstream_ghg=base_up[sc])
        out[sc][ef] = dict(fp=r['chain_corrected_t'] / 100.0, by_stage={k: v for k, v in r['stage_ghg_t'].items()}, dri=r['dri_line_t'])
# reconfiguration to a DRI-dominant route (57% of liquid steel from own cold DRI, 43% imported scrap), as in CARES EPD 0038
for share in (0.57,):
    lst_dri = 160 * share
    rc = dict(hdri=0, cdri=lst_dri / 0.92, hms1=(160 - lst_dri) * 0.6 / 0.93, hms2=(160 - lst_dri) * 0.4 / 0.89, gas=5,
              cdri_row=10, hms1_row=12, hms2_row=15, cao_row=20, mgo_row=32, c_row=42)
    o = evaluate(P, **rc)
    sc, o2 = recipe_to_m1(d['Baseline'], P, rc)
    res = {}
    for ef in (450, 706):
        r = E.run(sc, {'grid_ef': ef}, base_upstream_ghg=base_up['Baseline'])
        res[ef] = dict(fp=r['chain_corrected_t'] / 100.0, rebar_see=r['hr']['see'], dri_see=r['dr']['see'], by_stage=r['stage_ghg_t'], dri_line=r['dri_line_t'])
    out[f'dri_{share}'] = dict(recipe=rc, lst=float(o['lst']), slag=float(o['slag']), pon=float(o['pon']), wear=float(o['wear']),
                               feasible=bool(o['chk_ok']), elec_kwh_t=float(o['elec_kwh']) / 160, res=res)
json.dump(out, open(paths.out('validation_chapter7.json'), 'w'), indent=1, default=float)
for k, v in out.items():
    if k.startswith('dri'):
        print('DRI-dominant reconfiguration (57% DRI):', 'all checks met', v['feasible'], 'slag', round(v['slag'], 3), 'pon', round(v['pon'], 1), 'kWh/t', round(v['elec_kwh_t']), {ef: round(x['fp'], 3) for ef, x in v['res'].items()}, 'rebar SEE', round(v['res'][450]['rebar_see'], 3))
    else:
        print(f'{k:9s} cradle-to-gate footprint, kg CO2e per t rebar:', {f'grid {ef} g/kWh': round(x['fp'], 1) for ef, x in v.items()})
