"""Identical parallel active-pump energy comparison for one shared system.

For n pumps carrying equal flow, each provides Q_total/n at the SAME system
head H_sys(Q_total). This is a normal-duty hydraulic comparison only: no
standby, N+1 reliability, controls, redundancy, or failure simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from .pump import PumpSpec, SystemSpec, OperatingPoint, controlled_duty, minimum_feasible_speed, system_head_m


@dataclass(frozen=True)
class ParallelResult:
    active_pumps: int
    total_flow_m3h: float
    speed_ratio: float
    per_pump_duty: OperatingPoint
    combined_electric_kw: float
    specific_energy_kwh_m3: float


def parallel_duty(pump: PumpSpec, system: SystemSpec, total_flow_m3h: float, active_pumps: int, speed_ratio: float) -> ParallelResult:
    if not isinstance(active_pumps, int) or not 1 <= active_pumps <= 10:
        raise ValueError("Active pumps must be a whole number between 1 and 10.")
    if total_flow_m3h <= 0 or not isfinite(total_flow_m3h):
        raise ValueError("Total delivered flow must be positive and finite.")
    per_pump = total_flow_m3h / active_pumps
    shared_head = system_head_m(system, total_flow_m3h)
    idealized_system = SystemSpec(static_head_m=shared_head, resistance_coefficient=0.0)
    duty = controlled_duty(pump, idealized_system, per_pump, speed_ratio)
    combined = duty.electric_power_kw * active_pumps
    return ParallelResult(active_pumps, total_flow_m3h, speed_ratio, duty, combined, combined / total_flow_m3h)


def best_parallel_energy(
    pump: PumpSpec, system: SystemSpec, total_flow_m3h: float,
    active_pumps: int, min_speed: float, max_speed: float,
) -> ParallelResult:
    if max_speed < min_speed or min_speed <= 0:
        raise ValueError("Positive ordered speed bounds are required.")
    if not isinstance(active_pumps, int) or not 1 <= active_pumps <= 10:
        raise ValueError("Active pumps must be 1 to 10.")
    shared_head = system_head_m(system, total_flow_m3h)
    idealized_system = SystemSpec(static_head_m=shared_head, resistance_coefficient=0.0)
    feasible_min = max(min_speed, minimum_feasible_speed(pump, idealized_system, total_flow_m3h / active_pumps))
    if feasible_min > max_speed + 1e-10:
        raise ValueError("The configured speed range cannot supply the total flow with this pump count.")
    candidate_speeds = np.linspace(min(feasible_min, max_speed), max_speed, 121)
    return min(
        (parallel_duty(pump, system, total_flow_m3h, active_pumps, float(s)) for s in candidate_speeds),
        key=lambda result: result.combined_electric_kw,
    )
