"""Module 1 verification: recompute every scenario with module1_engine and compare production, direct,
precursor and attributed emissions, specific embedded emissions, chargeable emissions per tonne and
certificate cost with the 'Summary' tab of the workbook, for pellets, DRI, crude steel, rebar and
fabricated product.  Usage: python module1_verify.py [--m1 <file>]"""
import warnings
warnings.filterwarnings('ignore')
import openpyxl
import paths
import module1_engine as E

ROWMAP = {'Baseline': 7, 'S1': 15, 'S2': 23, 'S3': 31}                       # first Summary row of each scenario
PROCS = [('pellet', 0), ('dr', 1), ('crude', 4), ('hr', 5), ('fab', 7)]       # row offset of each product
COLS = dict(prod='D', direct='F', precursor_bought='H', internal='I', attributed='J', see='K', charge_per_t='M', cert='R')


def main():
    d = paths.module1_rows()
    S = openpyxl.load_workbook(paths.M1, data_only=True)['Summary']
    base_up = E.run(d['Baseline'])['upstream_ghg_kg']
    maxerr, n = 0.0, 0
    for sc, r0 in ROWMAP.items():
        res = E.run(d[sc], base_upstream_ghg=base_up)
        for pname, off in PROCS:
            for k, c in COLS.items():
                ref = S[f'{c}{r0 + off}'].value
                ref = float(ref) if isinstance(ref, (int, float)) else 0.0
                v = res[pname][k]
                err = abs(v - ref) / abs(ref) if abs(ref) > 1e-9 else abs(v)
                maxerr = max(maxerr, err); n += 1
                if err > 1e-6:
                    print('MISMATCH', sc, pname, k, v, ref)
        print(f"{sc:9s} rebar SEE {res['hr']['see']:.5f} t CO2e/t | chargeable {res['hr']['chargeable']:9.1f} t | "
              f"certificates USD {res['hr']['cert']:11,.0f} | chain footprint {res['chain_corrected_t']:9,.0f} t CO2e")
    print(f'{n} Summary values compared, largest relative error {maxerr:.1e}')
    return maxerr < 1e-6


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
