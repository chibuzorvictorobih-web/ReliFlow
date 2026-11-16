"""Deterministic uncertainty scenarios for a fixed decision, not confidence limits.

We do not infer distributions, prediction intervals, or causal speed-failure
relationships from synthetic data. Parameters are perturbed by user-entered
fractions while pump duty and the fixed maintenance decision stay unchanged.
"""
from __future__ import annotations

from .optimization import EconomicsSpec, StrategyMetrics, evaluate_strategy
from .pump import PumpSpec, SystemSpec
from .reliability import MaintenanceSpec, WeibullSpec


def reliability_sensitivity(
    pump: PumpSpec,
    system: SystemSpec,
    flow_m3h: float,
    reference_lifetime: WeibullSpec,
    maintenance: MaintenanceSpec,
    economics: EconomicsSpec,
    chosen: StrategyMetrics,
    shape_change_fraction: float = 0.15,
    life_change_fraction: float = 0.20,
    baseline: StrategyMetrics | None = None,
) -> list[dict]:
    if not (0 <= shape_change_fraction < 1 and 0 <= life_change_fraction < 1):
        raise ValueError("Uncertainty fractions must be between 0 and 1 (exclusive).")
    rows = []
    for shape_mult in (1 - shape_change_fraction, 1.0, 1 + shape_change_fraction):
        for life_mult in (1 - life_change_fraction, 1.0, 1 + life_change_fraction):
            scenario = WeibullSpec(
                reference_lifetime.shape * shape_mult,
                reference_lifetime.characteristic_life_hours * life_mult,
            )
            evaluated = evaluate_strategy(
                pump, system, flow_m3h, scenario, maintenance, economics,
                chosen.duty.speed_ratio, chosen.maintenance.interval_hours,
            )
            baseline_cost = None
            if baseline is not None:
                baseline_cost = evaluate_strategy(
                    pump, system, flow_m3h, scenario, maintenance, economics,
                    baseline.duty.speed_ratio, baseline.maintenance.interval_hours,
                ).annual_total_cost
            rows.append({
                "Weibull shape β": round(scenario.shape, 4),
                "Characteristic life η (h)": round(scenario.characteristic_life_hours, 1),
                "Availability (%)": round(100 * evaluated.maintenance.availability, 3),
                "Annual cost ($)": round(evaluated.annual_total_cost, 2),
                "Cost difference vs baseline ($)": None if baseline_cost is None else round(baseline_cost - evaluated.annual_total_cost, 2),
            })
    return rows
