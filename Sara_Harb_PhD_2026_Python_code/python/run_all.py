"""Run the three verifications in order: Module 1 against its Summary tab, Module 2 recipes and search against
the workbook tabs, and the coupling of the two modules.  Add --full to run the Chapter 6 and Chapter 7 analyses.
Usage: python run_all.py [--full] [--m1 <file>] [--m2 <file>]"""
import sys, runpy, time

STEPS = ['module1_verify', 'module2_verify', 'coupling_verify']
if '--full' in sys.argv:
    STEPS += ['validation_chapter7', 'sensitivity_chapter6', 'sensitivity_supplier_cap_and_grade']
failed = []
for s in STEPS:
    print(f'\n=== {s} ===', flush=True)
    t0 = time.time()
    try:
        runpy.run_module(s, run_name='__main__')
    except SystemExit as e:
        if e.code:
            failed.append(s)
    print(f'({time.time() - t0:.0f} s)')
print('\nAll verifications passed.' if not failed else f'\nFailed: {failed}')
raise SystemExit(1 if failed else 0)
