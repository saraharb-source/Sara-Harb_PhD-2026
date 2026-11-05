# Sara Harb, PhD 2026: Models and Code

This repository holds the two models of the dissertation and the Python code that verifies them and runs the
analyses of Chapters 6 and 7.

| File | What it is |
|---|---|
| `Sara_Harb_PhD_Thesis_Module_1.xlsx` | Module 1: stage-level emissions, CBAM attribution and cost along the seven stages of the DRI–EAF chain (Baseline, S1, S2, S3) |
| `Sara_Harb_PhD_Thesis_Module_2.xlsx` | Module 2: the EAF Charge Optimization Model (baseline, four optimization tabs, Suppliers Pool, Admin Setup, Solver entry) |
| `python/` | Independent Python implementation of both modules, the exhaustive supplier search and the verification and sensitivity scripts |

## Python code

| File | Role |
|---|---|
| `module2_engine.py` | Data layer and equation engine. `load_params()` reads every input from the *Admin Setup* and *Suppliers Pool* tabs; `evaluate()` computes Equations 1–42 (with 26b, 26c, 34b, 37b, 42b), the five feasibility checks, the supplier order ranges, the cost and emission register and the in-furnace process CO₂ |
| `module2_search.py` | Exhaustive search over the 17,496 supplier combinations (4 CDRI × 3 HMS1 × 3 HMS2 × 6 CaO × 9 MgO × 9 carbon), scanning the scrap split in 1 t steps of liquid steel and the burner rate from 0 to 12 Nm³/t; Pareto frontier; a search in which DRI is free to enter the charge |
| `module2_verify.py` | Evaluates the five recipes held in the workbook and re-runs the four searches from scratch; compares both with the TOTAL row of each tab (`--wide` also lets DRI enter the charge) |
| `module1_extract.py` | Reads the stage tables of Module 1 (Baseline, S1, S2, S3 × seven stages) |
| `module1_engine.py` | Recomputes the Module 1 chain: GHG footprint, CBAM direct, indirect and precursor emissions, specific embedded emissions, benchmarks, chargeable emissions and certificate cost |
| `module1_verify.py` | Compares 160 values with the *Summary* tab of Module 1 |
| `coupling.py`, `coupling_verify.py` | Shared register: writes a Module 2 recipe into the Module 1 EAF stage and checks that it reproduces the S1, S2, S3 and baseline scenario sets |
| `sensitivity_chapter6.py` | Chapter 6 sensitivity analysis: one-at-a-time, grid factor, certificate price by year, Monte Carlo (3,000 draws), re-optimization under changed conditions, internal carbon price and its switching prices, DRI-share sweep |
| `sensitivity_supplier_cap_and_grade.py` | Chapter 6 re-optimization when DRI must enter the charge: 40% supplier cap (compared with the *Supplier Cap Sensitivity* tab) and the hot-rolled coil grade |
| `validation_chapter7.py` | Chapter 7 footprint at two grid factors and the DRI-dominant reconfiguration |
| `run_all.py` | Runs the three verifications (add `--full` for the analyses) |

## Running it

Python 3.10 or later.

```
pip install -r python/requirements.txt
cd python
python run_all.py            # verifications, about 15 s
python run_all.py --full     # plus the Chapter 6 and 7 analyses (about 1.5 hours)
```

The scripts read the two workbooks from the repository root. Point them elsewhere with
`--m1 <file>` and `--m2 <file>`. Results are written to `python/output/`.

## What the verification shows

| Check | Result |
|---|---|
| Module 1, 160 values of the *Summary* tab | largest relative difference 3 × 10⁻¹⁵ |
| Module 2, five recipes held in the workbook | cost and emissions equal to the TOTAL row of every tab |
| Module 2 search, Lowest Cost | USD 64,647.53 and 71.531 t CO₂e a heat, same suppliers as the tab |
| Module 2 search, Lowest Emissions | USD 69,565.98 and 48.934 t CO₂e a heat, same suppliers as the tab |
| Module 2 search, Balanced (cost within 2% of the lowest) | USD 65,715.18 and 58.576 t CO₂e a heat, same suppliers as the tab |
| Module 2 search, Lowest Cost with HDRI floor (23.05 t) | USD 66,152.45 a heat at the 1 t step, same suppliers as the tab; the tab holds the same recipe with a finer split (USD 66,152.24) |
| Feasible recipes and Pareto frontier | 941,499 feasible recipes, 142 non-dominated |
| Coupling of the two modules | EAF footprint, crude-steel direct emissions and rebar chargeable emissions of S1, S2, S3 and the baseline reproduced |

## What the analyses reproduce

| Analysis | Result |
|---|---|
| Monte Carlo, 3,000 joint draws of eight inputs (seed 42) | ranking of the four recipes holds in 95.9% of draws on the border account and in all of them on the footprint |
| Internal carbon price on the footprint | the recipe switches at USD 72, 284 and 425 per t CO₂e; the least-emission recipe is selected above USD 425 |
| Moving from the least-cost to the least-emission recipe | USD 3.23 million a year; 14,739 t CO₂e of footprint (USD 219 per t) but 1,900 t of chargeable emissions (USD 1,702 per t) |
| Supplier cap at 40% (DRI free to enter, refined to 0.02 t) | lowest cost USD 66,127.16 and 106.55 t CO₂e a heat (tab: 66,127.10 and 106.44); lowest emissions USD 69,062.89 and 84.38 t CO₂e (tab: 69,062.98 and 84.37) |
| Hot-rolled coil grade | lowest cost USD 69,776 and 149.65 t CO₂e a heat; lowest emissions USD 69,944 and 117.66 t CO₂e |
