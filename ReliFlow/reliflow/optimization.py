"""Joint grid-based cost search for equal-flow speed and replacement policy.

No reliability-versus-speed correlation is asserted without test/field data.
The speed and maintenance decision variables influence annual cost through
energy consumption and expected uptime; the grid includes run-to-failure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .pump import PumpSpec, SystemSpec, OperatingPoint, controlled_duty, minimum_feasible_speed
from .reliability import WeibullSpec, MaintenanceSpec, MaintenanceMetrics, age_replacement


@dataclass(frozen=True)
class EconomicsSpec:
    annual_scheduled_hours: float = 8_000.0
    electricity_price_per_kwh: float = 0.14
    grid_emissions_kgco2_per_kwh: float = 0.45

    def __post_init__(self) -> None:
        if not (0 < self.annual_scheduled_hours <= 8784):
            raise ValueError("Annual scheduled hours must be within (0, 8784].")
        if self.electricity_price_per_kwh < 0 or self.grid_emissions_kgco2_per_kwh < 0:
            raise ValueError("Electricity price and emission factor cannot be negative.")


@dataclass(frozen=True)
class StrategyMetrics:
    duty: OperatingPoint
    maintenance: MaintenanceMetrics
    annual_uptime_hours: float
    expected_annual_volume_m3: float
    annual_electricity_kwh: float
    annual_energy_cost: float
    annual_maintenance_cost: float
    annual_downtime_cost: float
    annual_total_cost: float
    annual_emissions_kgco2: float


def evaluate_strategy(
    pump: PumpSpec,
    system: SystemSpec,
    required_flow_m3h: float,
    lifetime: WeibullSpec,
    maintenance: MaintenanceSpec,
    economics: EconomicsSpec,
    speed_ratio: float,
    pm_interval_hours: float | None,
) -> StrategyMetrics:
    duty = controlled_duty(pump, system, required_flow_m3h, speed_ratio)
    policy = age_replacement(lifetime, maintenance, pm_interval_hours)
    uptime = economics.annual_scheduled_hours * policy.availability
    electricity = uptime * duty.electric_power_kw
    energy_cost = electricity * economics.electricity_price_per_kwh
    maintenance_cost = economics.annual_scheduled_hours * policy.maintenance_cost_per_calendar_hour
    downtime_cost = economics.annual_scheduled_hours * policy.downtime_cost_per_calendar_hour
    return StrategyMetrics(
        duty=duty,
        maintenance=policy,
        annual_uptime_hours=uptime,
        expected_annual_volume_m3=uptime * required_flow_m3h,
        annual_electricity_kwh=electricity,
        annual_energy_cost=energy_cost,
        annual_maintenance_cost=maintenance_cost,
        annual_downtime_cost=downtime_cost,
        annual_total_cost=energy_cost + maintenance_cost + downtime_cost,
        annual_emissions_kgco2=electricity * economics.grid_emissions_kgco2_per_kwh,
    )


def optimize_strategy(
    pump: PumpSpec,
    system: SystemSpec,
    required_flow_m3h: float,
    lifetime: WeibullSpec,
    maintenance: MaintenanceSpec,
    economics: EconomicsSpec,
    min_speed: float,
    max_speed: float,
    min_pm_hours: float,
    max_pm_hours: float,
    n_speeds: int = 201,
    n_pm_intervals: int = 181,
) -> StrategyMetrics:
    """Global minimum across a disclosed finite grid and run-to-failure option.

    Includes the analytical minimum feasible speed exactly and candidate end
    points. This is a decision-support grid, not a continuous global proof.
    """
    if min_speed <= 0 or max_speed < min_speed:
        raise ValueError("Speed bounds must be positive and ordered.")
    if min_pm_hours <= 0 or max_pm_hours < min_pm_hours:
        raise ValueError("PM interval bounds must be positive and ordered.")
    if n_speeds < 2 or n_pm_intervals < 2:
        raise ValueError("Optimization grids must contain at least two points per axis.")
    feasible_min = max(min_speed, minimum_feasible_speed(pump, system, required_flow_m3h))
    if feasible_min > max_speed + 1e-12:
        raise ValueError(
            "No speed in the permitted range can deliver the required flow. "
            f"Required minimum: {feasible_min:.1%}, permitted maximum: {max_speed:.1%}."
        )
    feasible_min = min(feasible_min, max_speed)
    speeds = np.linspace(feasible_min, max_speed, n_speeds)
    intervals = [float(t) for t in np.geomspace(min_pm_hours, max_pm_hours, n_pm_intervals)]
    intervals.append(None)  # explicit run-to-failure competitor

    # Construct grid of cost components; work in float64 to avoid overflow.
    power = np.array([
        controlled_duty(pump, system, required_flow_m3h, float(s)).electric_power_kw
        for s in speeds
    ], dtype=float)
    policies = [age_replacement(lifetime, maintenance, t) for t in intervals]
    avail = np.array([p.availability for p in policies])
    maintenance_rates = np.array([p.maintenance_cost_per_calendar_hour for p in policies])
    downtime_rates = np.array([p.downtime_cost_per_calendar_hour for p in policies])

    annual = economics.annual_scheduled_hours
    combined_cost = (
        annual * economics.electricity_price_per_kwh * power[:, None] * avail[None, :]
        + annual * maintenance_rates[None, :]
        + annual * downtime_rates[None, :]
    )
    speed_idx, pm_idx = np.unravel_index(int(np.argmin(combined_cost)), combined_cost.shape)
    return evaluate_strategy(
        pump, system, required_flow_m3h, lifetime, maintenance, economics,
        float(speeds[speed_idx]), intervals[pm_idx],
    )
