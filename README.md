# ReliFlow

### Industrial Equipment Reliability & Energy Optimization

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-0C766B)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**ReliFlow** is an independent, reproducible computational engineering case
study that joins steady-state **centrifugal pump hydraulics**, **energy-use
modeling**, **Weibull reliability**, and **age-replacement maintenance
optimization** in one interactive decision-support application.

Its key engineering question is:

> For a fixed required volumetric flow, which allowable pump speed and
> planned replacement interval minimize expected annual energy, maintenance,
> and production-downtime costs?

This is an **educational engineering portfolio project**. All three starting
scenarios and displayed costs are **synthetic illustrations**, not observations
from any refinery or other real industrial facility. It is not for engineering
sign-off, operational control, or safety-critical use.

## What the application does

- Simulates a pump head curve and a static-plus-friction system curve at variable speed.
- Finds open-valve operating points (pump and system curve intersections).
- Computes **fixed-demand controlled operating points** (with any excess head
  lost through an idealized throttling valve) for honest speed comparisons.
- Estimates hydraulic, shaft, and electrical performance from an editable
  BEP-based pump-efficiency approximation and motor/drive efficiencies.
- Models lifetime survival and conditional reliability using a two-parameter
  Weibull distribution, including time-dependent hazard and mean life.
- Models expected uptime, expected repair/replacement downtime, and maintenance
  cost using a **renewal-reward age-replacement policy**.
- Searches allowable speed and replacement interval combinations, including
  **run-to-failure**, for lowest annual modeled total cost.
- Compares the nominal 100% speed baseline, a selected speed, and optimized
  settings; includes a clear warning for hydraulically infeasible settings.
- Exports scenario assumptions (**JSON**), strategy comparison (**CSV**),
  and a 900-row sensitivity grid (**CSV**).
- Includes 23 analytical/regression tests and a GitHub Actions workflow.

## Update in v1.1.0 (16 November 2026)

- A **Calculate & Optimize** button now submits all sidebar inputs together; the expensive search does not run on every edit.
- The dashboard starts with simple instructions and displays results **after** the button is pressed.
- Results are retained through Streamlit reruns and CSV/JSON downloads. Changing the illustrative scenario prompts a new calculation before showing any results for it.
- Added a consistent dark Streamlit theme and dark metric cards with readable labels and values.
- The engineering equations and synthetic example assumptions are unchanged by this interface update.

**How to use:** Select a scenario → adjust the sidebar values → press **🧮 Calculate & Optimize** → explore the tabs and download results. If you change the inputs, press the button again to update the results.

## Fix in v1.0.1 (16 November 2026)

Streamlit requires the default `value`, `min_value`, `max_value` and `step` of
`st.number_input` to use compatible numeric types. The widget wrapper in
`app.py` now consistently supplies floats, preventing the
`StreamlitMixedNumericTypesError` that occurred for speed percentage inputs
with integer limits. Regression tests check all sidebar number widgets across
the three illustrative presets.

## Dashboard views

| Tab | Included analysis |
| --- | --- |
| **Overview** | Optimized recommendations, cost breakdown, strategy comparison |
| **Pump & energy** | Pump/system curve intersections, controlled duty, power and kWh/m³ sweep |
| **Reliability** | Weibull survival, instantaneous hazard, conditional survival, availability vs interval |
| **Optimization & exports** | Strategy comparison, objective landscape, exports |
| **Methods & limitations** | Equations, assumptions, external engineering references |

## Run locally

Install [Python 3.11+](https://www.python.org/downloads/) and run in the project
root (the folder containing `app.py`).

**Windows (Command Prompt / CMD)**

Open CMD in the folder containing `app.py`, then run:

```bat
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

To run automated tests, install `requirements-dev.txt` and run `py -m pytest -q`.

**Windows (PowerShell, optional virtual environment)**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Your browser will normally open at `http://localhost:8501`.

### Publish to GitHub

1. Create a new GitHub repository, for example **ReliFlow**.
2. **Extract the supplied ZIP archive**. Upload the *contents* of the
   `ReliFlow` folder to the repository root: `app.py`, `requirements.txt`,
   `reliflow/`, `tests/`, `examples/`, `.github/`, `.streamlit/` etc. (GitHub
   does not automatically unpack a ZIP uploaded through its browser interface.)
3. Commit the files. Ensure the hidden folders `.streamlit` and `.github` are
   included if you upload from a local Git client; they provide UI styling and CI.
4. To publish the interactive dashboard, go to
   [Streamlit Community Cloud](https://share.streamlit.io/), link the GitHub
   repository and choose `app.py` as the entry point. No API key is needed.
5. The GitHub Actions workflow `.github/workflows/tests.yml` installs the dev
   requirements and runs the tests on pushes/pull requests.

Your published app link will be assigned **after deployment**. This repository
contains no claim that a live app already exists.

## Reproduce the numerical reference case

The example inputs are in `reliflow/presets.py`.

```bash
python scripts/generate_example.py
```

This regenerates `examples/reference_results.csv` and
`examples/reference_results.json`. For a brief interpretation, see
[`CASE_STUDY.md`](CASE_STUDY.md).

## Model formulation

### 1. Pump and system head

Let `Q` be volumetric flow in m³/h and `s = n/n_ref` be pump speed ratio.
For a **fixed impeller** and an illustrative quadratic reference curve:

```text
Pump head:         H_pump(Q, s) = H_0*s² - a*Q²
System head:       H_sys(Q)     = H_static + k*Q²
Open-valve flow:   Q_open       = sqrt[(H_0*s²-H_static)/(a+k)]
Min feasible speed for Q_d:
                   s_min        = sqrt[(H_static+(a+k)*Q_d²)/H_0]
```

`H_0` is reference shutoff head (m); `a` and `k` are quadratic
coefficients in m/(m³/h)². If `H_0*s² <= H_static`, no forward-flow
open-valve intersection is returned. A demand greater than pump capability is
**infeasible** rather than silently rescaled.

For comparisons **at the same delivered flow `Q_d`**, available head
`H_pump(Q_d,s)` must be at least `H_sys(Q_d)`. Surplus head is modeled as
loss across a hypothetical throttle valve:

```text
H_throttle = max(0, H_pump(Q_d,s) - H_sys(Q_d))
```

This distinction is essential: merely lowering pump speed lowers
throughput, so comparing uncontrolled annual kWh would not establish
energy efficiency gains at an equal duty.

### 2. Energy and efficiency

The illustrative efficiency curve centers on best efficiency point (BEP):

```text
eta_pump(Q,s) = clip[
    eta_BEP - c*(Q/(Q_BEP*s)-1)²,
    lower=0.15, upper=eta_BEP
]

P_electric (kW) = rho*g*(Q/3600)*H_pump(Q,s)
                  / (1000*eta_pump*eta_motor*eta_VSD)
Specific energy (kWh/m³) = P_electric (kW) / Q (m³/h)
```

Here `rho` is fluid density (kg/m³) and `g=9.80665 m/s²`. Annual expected
electricity consumption equals input kW times expected available operating
hours; emissions use an **editable** kg CO₂/kWh factor. The efficiency map is
**invented for illustration**, not fitted to vendor data. At real installations
replace it with verified performance curves.

### 3. Weibull reliability

For operating age `t`, characteristic life `eta` and shape `beta`:

```text
R(t)     = exp[-(t/eta)^beta]
h(t)     = (beta/eta)*(t/eta)^(beta-1)
MTTF     = eta*Gamma(1+1/beta)
R(t|a)   = exp[-((a+t)/eta)^beta+(a/eta)^beta]
```

`R(t|a)` is the probability of surviving an additional `t` operating hours
conditional on having reached age `a`. **MTTF** refers to a fresh-item
lifetime and is not mislabeled as a repairable-system MTBF.

### 4. Age-replacement maintenance policy

A planned replacement happens at operating age `T` if the pump has survived.
Otherwise a failure is repaired before that age. After **either event** the
component is assumed to return to *as-new* condition. With `R(T)` the
probability of reaching `T`:

```text
E[uptime per renewal cycle] = ∫(0 to T) R(t)dt
                            = eta/beta * Gamma(1/beta)
                              * P(1/beta, (T/eta)^beta)

E[downtime per cycle] = R(T)*d_PM + (1-R(T))*d_CM

A(T) = E[uptime] / (E[uptime]+E[downtime])

Cost of maintenance per calendar hour =
    [R(T)*C_PM + (1-R(T))*C_CM]
    / [E[uptime]+E[downtime]]

Cost of outage per calendar hour = [1-A(T)]*C_outage_hour
```

`P` is the **regularized lower incomplete gamma function**, used with
`Gamma` to evaluate the expected operating interval. For **run to failure**,
`E[uptime]=MTTF`, repair downtime is `d_CM`, and corrective maintenance cost
is `C_CM`. This policy is explicitly included as a candidate.

### 5. Annual objective and search

```text
Annual available operation = H_scheduled * A(T)
Annual volume delivered     = Q_d * Annual available operation
Annual energy cost          = kW(Q_d,s) * Annual available operation * electricity_price
Annual maintenance cost     = H_scheduled * maintenance_cost_per_calendar_hour
Annual outage penalty       = H_scheduled * (1-A(T)) * outage_cost_per_hour
Annual total objective      = sum of above three annual cost components
```

By default, speed is evaluated at **201 points** and PM intervals at
**181 logarithmically spaced points** plus a run-to-failure candidate.
The analytical hydraulic minimum speed is included exactly. This finds the
lowest cost on the **declared finite grid**, not a proven global solution to
all possible real-world settings. Parameters are adjustable in the sidebar.

## Verification

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Validation checks include:

- Pump affinity scaling of corresponding reference-flow points.
- Analytical open-valve curve intersection and hydraulic feasibility.
- Direct SI-unit hydraulic/electric power calculation.
- Constant-demand power comparison (not a misleading change in flow).
- Weibull exponential special case (`beta=1`) and closed-form MTTF.
- Conditional reliability identity.
- Age-replacement uptime integral and renewal cost identities.
- Limiting run-to-failure behavior and infeasible optimization constraints.
- Optimization cost accounting and a reproducible regression example.

## Assumptions and limitations

1. **No proprietary data:** all presets are fictitious. Use plant-approved
   data only with the appropriate authorization.
2. **Simplified hydraulics:** steady state only; no transient/water hammer,
   cavitation, NPSH, minimum-flow recirculation, viscosity effects, suction
   limitations, multiple parallel pumps, pump runout, or electrical overload.
3. **Synthetic efficiency map:** the full range can be inaccurate, especially
   away from BEP or at extreme speeds. No motor or seal rating constraints
   are enforced beyond the user-specified speed bounds.
4. **Independent reliability and hydraulic performance:** there is **no
   asserted causal effect** of speed on failure-rate parameters without
   field evidence.
5. **Simplified maintenance:** independent lifetimes, as-new renewal after
   replacement or corrective repair, constant intervention downtime and
   cost, no partial degradation or imperfect repairs.
6. **Expected values:** annual figures use stationary renewal averages and
   constant required flow, not a time-series Monte Carlo simulation.
7. **Illustrative economics:** prices, emissions factor, and outage penalty
   are adjustable assumptions, not observed site or national statistics.
   A reduction in annual emissions is not automatically comparable across
   scenarios with different annual delivered volumes. Prefer per-m³ numbers.
8. **Not for plant decisions:** verify pump curves, duty limits, NPSH,
   operating constraints, risk tolerances, relevant standards, and model
   assumptions before any real equipment decision.

## Engineering sources

- [Hydraulic Institute: Pump Curves / Affinity Rules](https://datatool.pumps.org/pump-fundamentals/pump-curves.html)
- [U.S. DOE: Variable Speed Pumping — A Guide to Successful Applications](https://www.energy.gov/sites/prod/files/2014/05/f16/variable_speed_pumping.pdf)
- [U.S. DOE: Improving Pumping System Performance](https://www.energy.gov/sites/prod/files/2014/05/f16/pump.pdf)
- [NIST/SEMATECH: Weibull lifetime distribution and reliability](https://www.itl.nist.gov/div898/handbook/apr/section1/apr162.htm)

These references underpin the general methods. ReliFlow's default numerical
coefficients and example economics are **not** derived from these references.

## Project structure

```text
ReliFlow/
├── app.py                      # Streamlit dashboard
├── reliflow/
│   ├── __init__.py
│   ├── pump.py                 # Head curves, speed, duty energy
│   ├── reliability.py          # Weibull + age-replacement calculations
│   ├── optimization.py         # Annual economics and finite grid search
│   └── presets.py              # Fully synthetic example input scenarios
├── tests/
│   ├── test_pump.py
│   ├── test_reliability.py
│   ├── test_optimization.py
│   └── test_ui_inputs.py        # Streamlit numeric-type regression checks
├── scripts/
│   └── generate_example.py     # Reproducible command-line case study
├── examples/
│   ├── reference_results.csv
│   ├── reference_results.json
│   └── README.md
├── .streamlit/config.toml      # Theme
├── .github/workflows/tests.yml # CI
├── requirements.txt
├── requirements-dev.txt
├── CASE_STUDY.md
├── LICENSE
└── .gitignore
```

## License

[MIT](LICENSE). Project outputs are estimates based on user-supplied assumptions;
there is no warranty of fitness for any specific engineering purpose.
