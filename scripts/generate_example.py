"""Regenerate the included cooling-water reference case, without Streamlit.

Run from the repository root:
    python scripts/generate_example.py
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Allow execution from the repository root without pip installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reliflow.optimization import EconomicsSpec, evaluate_strategy, optimize_strategy  # noqa: E402
from reliflow.presets import PRESETS  # noqa: E402
from reliflow.pump import PumpSpec, SystemSpec, minimum_feasible_speed  # noqa: E402
from reliflow.reliability import MaintenanceSpec, WeibullSpec  # noqa: E402


def run() -> None:
    data = PRESETS["Cooling-water circulation (illustrative)"]
    pump = PumpSpec(**{name: data[name] for name in PumpSpec.__dataclass_fields__})
    system = SystemSpec(**{name: data[name] for name in SystemSpec.__dataclass_fields__})
    life = WeibullSpec(**{name: data[name] for name in WeibullSpec.__dataclass_fields__})
    maintenance = MaintenanceSpec(**{name: data[name] for name in MaintenanceSpec.__dataclass_fields__})
    economics = EconomicsSpec(**{name: data[name] for name in EconomicsSpec.__dataclass_fields__})
    q = data["required_flow_m3h"]

    baseline = evaluate_strategy(
        pump, system, q, life, maintenance, economics, 1.0, data["baseline_pm_interval"]
    )
    optimized = optimize_strategy(
        pump, system, q, life, maintenance, economics,
        data["min_speed_percent"] / 100, data["max_speed_percent"] / 100,
        data["pm_min_hours"], data["pm_max_hours"],
    )
    rows = []
    for name, scenario in (("Baseline", baseline), ("Optimized", optimized)):
        rows.append({
            "strategy": name,
            "flow_m3h": q,
            "reference_speed_percent": round(100 * scenario.duty.speed_ratio, 3),
            "pm_interval_operating_hours": scenario.maintenance.interval_hours or "run_to_failure",
            "electrical_kw": round(scenario.duty.electric_power_kw, 4),
            "specific_energy_kwh_per_m3": round(scenario.duty.specific_energy_kwh_m3, 5),
            "availability_percent": round(100 * scenario.maintenance.availability, 3),
            "expected_annual_volume_m3": round(scenario.expected_annual_volume_m3, 1),
            "annual_total_cost_assumed_usd": round(scenario.annual_total_cost, 2),
        })
    output = ROOT / "examples"
    output.mkdir(exist_ok=True)
    with (output / "reference_results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    dump = {
        "note": "All inputs and numerical outputs are synthetic illustrative modeling estimates.",
        "pump": asdict(pump), "system": asdict(system),
        "lifetime": asdict(life), "maintenance": asdict(maintenance),
        "economics": asdict(economics), "required_flow_m3h": q,
        "minimum_feasible_speed_ratio": minimum_feasible_speed(pump, system, q),
        "baseline": asdict(baseline), "optimized": asdict(optimized),
    }
    with (output / "reference_results.json").open("w", encoding="utf-8") as file:
        json.dump(dump, file, indent=2, allow_nan=False)
        file.write("\n")
    print("Saved: examples/reference_results.csv and examples/reference_results.json")
    print(f"Same-demand specific-energy reduction: {100*(1 - optimized.duty.specific_energy_kwh_m3/baseline.duty.specific_energy_kwh_m3):.2f}%")
    print(f"Estimated annual combined cost difference: ${baseline.annual_total_cost - optimized.annual_total_cost:,.2f}")


if __name__ == "__main__":
    run()
