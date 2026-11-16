# ReliFlow: Reproducible Engineering Case Study

## Additional educational diagnostics

This enhanced build retains the same **v1.1.0** version label and preserves the
original pump-cost case study. The optional NPSH screen uses assumed pressure,
vapor pressure, liquid elevation, suction losses and NPSHr with a squared-speed
approximation; it should not be interpreted as a vendor-verified cavitation limit.
The heatmap visualizes the original synthetic pump efficiency relation.

A parallel-pump comparison approximates the electrical input for one to three
identical active pumps at the same total system flow and head; it does not
simulate standby systems or availability. A nine-scenario Weibull sensitivity
table varies the assumed lifetime distribution while holding the recommended
speed and maintenance strategy fixed. These are deterministic scenarios, not
confidence intervals.

An exportable PDF contains the engineering results, assumptions and limitations.
All source values remain educational examples rather than measured plant data.

## Problem statement

An illustrative centrifugal pump supplies a cooling-water circuit. The
process requires **70 m³/h**. Running the pump at nominal 100% speed
provides more head than the circuit actually needs; a control valve must
absorb the surplus. Meanwhile, corrective failures and preventive
replacement interventions create cost and unserved production time.

**Research question:** Using a fixed required delivered flow, how much can
energy intensity and combined maintenance/availability economics change
under a joint pump-speed and replacement-interval search?

The model represents **one pump and one flow requirement**. No numbers in
this report are actual industrial plant operating data.

## Input assumptions (invented for this demonstration)

| Parameter | Value |
| --- | ---: |
| Required delivered flow | 70 m³/h |
| Reference-speed shutoff head | 90 m |
| Reference pump head coefficient | 0.0065 m/(m³/h)² |
| System static head | 22 m |
| System friction coefficient | 0.0030 m/(m³/h)² |
| Best-efficiency-point flow | 80 m³/h |
| BEP pump efficiency | 82% |
| Motor / VSD efficiencies | 94% / 97% |
| Fluid density | 998 kg/m³ |
| Reference baseline speed | 100% |
| Baseline preventive interval | 7,500 operating hours |
| Weibull shape, scale | β = 2.2, η = 10,000 h |
| Preventive intervention | 6 h, assumed $550 |
| Corrective repair | 48 h, assumed $5,000 |
| Unserved-time penalty | assumed $650 per hour |
| Operating schedule | 8,000 calendar hours/year |
| Electricity price | assumed $0.14/kWh |
| Grid emissions factor | assumed 0.45 kg CO₂/kWh |
| Speed search | 65–115% nominal |
| PM interval search | 500–25,000 operating hours, plus run-to-failure |

## Method

1. Define pump curve `H_p(Q,s)=90 s²−0.0065 Q²` and system curve
   `H_sys(Q)=22+0.0030 Q²` in metres with `Q` in m³/h.
2. Require the *same delivered* `Q=70 m³/h` for every candidate speed.
   Additional pump head is interpreted as throttling loss.
3. Obtain electrical input from `rho*g*Q*H` divided by pump, motor and VSD
   efficiency. Calculate specific electrical energy (kWh/m³).
4. Use the two-parameter Weibull survival function to evaluate expected
   uptime before planned age replacement or an earlier failure.
5. Use renewal-reward averages for equipment availability, maintenance cost
   and downtime expense. Include an explicit run-to-failure alternative.
6. Search **201 speeds × (181 scheduled intervals + run-to-failure)** for the
   smallest modeled annual combined cost.

## Baseline vs optimized model output

Rounded values generated from `python scripts/generate_example.py`:

| Output | Reference baseline | Model-selected strategy |
| --- | ---: | ---: |
| Pump speed (% of reference) | 100.0% | **87.27%** |
| Planned interval | 7,500 h | **3,774 h** |
| Required delivered flow | 70 m³/h | 70 m³/h |
| System head required | 36.70 m | 36.70 m |
| Pump head at delivered flow | 58.15 m | 36.70 m |
| Surplus head dissipated by throttling | 21.45 m | 0.00 m |
| Electric input power | 14.90 kW | 9.34 kW |
| Specific electrical energy | 0.21286 kWh/m³ | 0.13345 kWh/m³ |
| Expected long-run availability | 99.639% | 99.708% |
| Expected delivered volume per year | 557,977 m³ | 558,367 m³ |
| Annual energy cost | $16,628 | $10,432 |
| Annual maintenance cost | $2,955 | $2,284 |
| Annual unserved-time cost | $18,782 | $15,161 |
| **Total modeled annual cost** | **$38,365** | **$27,877** |

**Key comparison:** Specific energy is reduced by approximately **37.31%**
when the modeled variable-speed control strategy meets the **same nominal
flow**, compared with reference-speed throttling.

The modeled combined annual objective is lower by approximately
**$10,488** (about 27.3%). This result incorporates *assumed* repair costs,
electricity tariff and downtime penalty. It should not be interpreted as a
verified saving at any actual industrial facility.

## Why compare specific energy instead of annual kWh alone?

The two maintenance policies have different expected equipment availability,
and thus produce slightly different expected yearly volume. Therefore annual
energy and emissions totals do not represent perfectly matched lifetime
throughput. The **kWh/m³** comparison uses a fixed duty rate and is more
suitable for assessing the hydraulic/control effect independently.

## Interpretation and engineering insight

- **System-level hydraulic control matters.** At 100% nominal speed and the
  required demand, the assumed pump produces excess head that is lost in a
  valve. The selected lower speed nearly eliminates this modeled loss.
- **Maintenance and energy are both relevant.** Weibull shape `β > 1`
  represents an increasing age-dependent failure hazard in this example. A
  moderate preventive interval can reduce assumed repair and outage cost.
- **Feasible does not mean safe.** The optimizer checks steady-state hydraulic
  capability and the configured speed bounds only. It does not check
  cavitation, vibration, minimum continuous stable flow, thermal limits,
  mechanical seal limits, startup conditions or pressure safety.
- **Uncertainty is material.** No confidence intervals or calibration data
  are provided. Real design decisions require measured pump curves, reliability
  records, maintenance data, actual outage costs and sensitivity assessment.

## Reproducibility and verification

Run:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/generate_example.py
streamlit run app.py
```

Review numerical source output in `examples/reference_results.json`, and
adjust all assumptions interactively in the Streamlit sidebar. The dashboard
also exports a compact 900-case sensitivity grid for independent analysis.

## Engineering references

- [Hydraulic Institute — pump affinity laws](https://datatool.pumps.org/pump-fundamentals/pump-curves.html)
- [DOE — Variable Speed Pumping](https://www.energy.gov/sites/prod/files/2014/05/f16/variable_speed_pumping.pdf)
- [NIST — Weibull reliability model](https://www.itl.nist.gov/div898/handbook/apr/section1/apr162.htm)

**Scope:** Educational simulation only. All results are conditional on
synthetic assumptions and must not be used as real-plant performance claims.
