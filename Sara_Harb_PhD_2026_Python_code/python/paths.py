"""Default locations.  The two workbooks sit in the repository root, one level above this folder; results are
written to python/output.  Any script accepts other workbook paths as --m1 <file> and --m2 <file>."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'output')


def _arg(flag, default):
    a = sys.argv
    return a[a.index(flag) + 1] if flag in a else default


M1 = _arg('--m1', os.path.join(ROOT, 'Sara_Harb_PhD_Thesis_Module_1.xlsx'))
M2 = _arg('--m2', os.path.join(ROOT, 'Sara_Harb_PhD_Thesis_Module_2.xlsx'))
os.makedirs(OUT, exist_ok=True)


def out(name):
    return os.path.join(OUT, name)


def module1_rows():
    """Module 1 stage tables as a dict; extracted from the workbook on first use and cached in output/."""
    import json
    p = out('module1_rows.json')
    if not os.path.exists(p) or os.path.getmtime(p) < os.path.getmtime(M1):
        from module1_extract import extract
        json.dump(extract(M1), open(p, 'w'), indent=1, default=str)
    return json.load(open(p))
