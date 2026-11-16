"""Steady-state centrifugal-pump system model with consistent SI units.

Flow inputs are m³/h, head inputs are metres, and power outputs are kW.
The curve uses the speed-affinity transformation for a fixed impeller.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

G = 9.80665  # m/s², conventional standard gravitational acceleration


@dataclass(frozen=True)
class PumpSpec:
    shutoff_head_m: float = 90.0
    head_curve_coefficient: float = 0.0065  # m/(m³/h)²
    bep_flow_m3h: float = 80.0
    bep_efficiency: float = 0.82
    efficiency_penalty: float = 0.35
    motor_efficiency: float = 0.94
    drive_efficiency: float = 0.97
    density_kg_m3: float = 998.0

    def __post_init__(self) -> None:
        if self.shutoff_head_m <= 0 or self.head_curve_coefficient <= 0:
            raise ValueError("Pump shutoff head and curve coefficient must be positive.")
        if self.bep_flow_m3h <= 0 or self.density_kg_m3 <= 0:
            raise ValueError("BEP flow and fluid density must be positive.")
        if not (0 < self.bep_efficiency <= 1):
            raise ValueError("BEP efficiency must be between 0 and 1.")
        if self.efficiency_penalty < 0:
            raise ValueError("Efficiency penalty must be nonnegative.")
        if not (0 < self.motor_efficiency <= 1 and 0 < self.drive_efficiency <= 1):
            raise ValueError("Motor/drive efficiencies must each be within (0, 1].")


@dataclass(frozen=True)
class SystemSpec:
    static_head_m: float = 22.0
    resistance_coefficient: float = 0.003  # m/(m³/h)²

    def __post_init__(self) -> None:
        if self.static_head_m < 0 or self.resistance_coefficient < 0:
            raise ValueError("Static head and system-resistance coefficient cannot be negative.")


@dataclass(frozen=True)
class OperatingPoint:
    flow_m3h: float
    system_head_m: float
    pump_head_m: float
    throttling_head_m: float
    pump_efficiency: float
    electric_power_kw: float
    specific_energy_kwh_m3: float
    speed_ratio: float


def pump_head_m(pump: PumpSpec, flow_m3h: float, speed_ratio: float) -> float:
    """Idealized H(Q,s) = H_shutoff*s² - a*Q² (metres)."""
    if flow_m3h < 0 or speed_ratio <= 0:
        raise ValueError("Flow cannot be negative and speed ratio must be positive.")
    return pump.shutoff_head_m * speed_ratio**2 - pump.head_curve_coefficient * flow_m3h**2


def system_head_m(system: SystemSpec, flow_m3h: float) -> float:
    if flow_m3h < 0:
        raise ValueError("Flow cannot be negative.")
    return system.static_head_m + system.resistance_coefficient * flow_m3h**2


def free_flow_point(pump: PumpSpec, system: SystemSpec, speed_ratio: float) -> tuple[float, float] | None:
    """Unthrottled pump/system intersection, or None when shutoff head is insufficient."""
    if speed_ratio <= 0:
        raise ValueError("Speed ratio must be positive.")
    numerator = pump.shutoff_head_m * speed_ratio**2 - system.static_head_m
    if numerator <= 0:
        return None
    q = sqrt(numerator / (pump.head_curve_coefficient + system.resistance_coefficient))
    return q, system_head_m(system, q)


def minimum_feasible_speed(pump: PumpSpec, system: SystemSpec, required_flow_m3h: float) -> float:
    """Minimum speed to deliver required flow WITHOUT throttling (pump head = system head)."""
    if required_flow_m3h <= 0:
        raise ValueError("Required flow must be positive.")
    required_shutoff = system.static_head_m + (
        system.resistance_coefficient + pump.head_curve_coefficient
    ) * required_flow_m3h**2
    return sqrt(required_shutoff / pump.shutoff_head_m)


def pump_efficiency(pump: PumpSpec, flow_m3h: float, speed_ratio: float) -> float:
    """Illustrative BEP-centered efficiency map, bounded to avoid invalid division."""
    if flow_m3h < 0 or speed_ratio <= 0:
        raise ValueError("Flow cannot be negative and speed ratio must be positive.")
    relative_flow = flow_m3h / (pump.bep_flow_m3h * speed_ratio)
    nominal = pump.bep_efficiency - pump.efficiency_penalty * (relative_flow - 1.0) ** 2
    return max(0.15, min(pump.bep_efficiency, nominal))


def controlled_duty(
    pump: PumpSpec, system: SystemSpec, required_flow_m3h: float, speed_ratio: float
) -> OperatingPoint:
    """Fixed-demand duty with a control valve absorbing any surplus pump head.

    This puts baseline and VSD scenarios on an equal-flow basis. An infeasible
    speed raises ValueError rather than fabricating flow or energy savings.
    """
    if required_flow_m3h <= 0:
        raise ValueError("Required flow must be positive.")
    available = pump_head_m(pump, required_flow_m3h, speed_ratio)
    required = system_head_m(system, required_flow_m3h)
    if available + 1e-8 < required:
        minimum = minimum_feasible_speed(pump, system, required_flow_m3h)
        raise ValueError(
            f"At {speed_ratio:.1%} speed, the pump cannot meet {required_flow_m3h:g} m³/h. "
            f"Minimum theoretical feasible speed: {minimum:.1%}."
        )
    efficiency = pump_efficiency(pump, required_flow_m3h, speed_ratio)
    q_m3s = required_flow_m3h / 3600.0
    hydraulic_kw = pump.density_kg_m3 * G * q_m3s * available / 1000.0
    electrical_kw = hydraulic_kw / (
        efficiency * pump.motor_efficiency * pump.drive_efficiency
    )
    return OperatingPoint(
        flow_m3h=required_flow_m3h,
        system_head_m=required,
        pump_head_m=available,
        throttling_head_m=max(0.0, available - required),
        pump_efficiency=efficiency,
        electric_power_kw=electrical_kw,
        specific_energy_kwh_m3=electrical_kw / required_flow_m3h,
        speed_ratio=speed_ratio,
    )
