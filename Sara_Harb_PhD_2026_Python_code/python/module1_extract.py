"""Module 1: read every populated row of every stage table (Baseline, S1, S2, S3 x seven stages) from the
cached values of Sara_Harb_PhD_Thesis_Module_1.xlsx.  Usage: python module1_extract.py [--m1 <file>]"""
import json, warnings
warnings.filterwarnings('ignore')
import openpyxl
from openpyxl.utils import range_boundaries

STAGES = ['Pelletizing', 'DRP', 'EAF', 'Secondary Metallurgy', 'Continuous Casting', 'Rolling Mill', 'Fabrication']
SETS = {'Baseline': '', 'S1': ' S1', 'S2': ' S2', 'S3': ' S3'}      # sheet-name suffix of each scenario


def extract(path):
    wbv = openpyxl.load_workbook(path, data_only=True)     # values
    wbf = openpyxl.load_workbook(path)                     # table definitions
    data = {}
    for sc, suf in SETS.items():
        data[sc] = {}
        for st in STAGES:
            shf, shv = wbf[st + suf], wbv[st + suf]
            data[sc][st] = {}
            for tname in shf.tables.keys():
                c1, r1, c2, r2 = range_boundaries(shf.tables[tname].ref)
                hdr = [shv.cell(r1, c).value for c in range(c1, c2 + 1)]
                rows = []
                for r in range(r1 + 1, r2 + 1):
                    vals = [shv.cell(r, c).value for c in range(c1, c2 + 1)]
                    if any(isinstance(v, (int, float)) and v != 0 for v in vals):
                        rec = {str(h): v for h, v in zip(hdr, vals)}
                        rec['_row'] = r
                        rows.append(rec)
                data[sc][st][tname] = {'header': [str(h) for h in hdr], 'rows': rows}
    return data


if __name__ == '__main__':
    import paths
    json.dump(extract(paths.M1), open(paths.out('module1_rows.json'), 'w'), indent=1, default=str)
    print('written', paths.out('module1_rows.json'))
