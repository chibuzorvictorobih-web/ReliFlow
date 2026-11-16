"""Illustrative suction-side NPSH screening; not a manufacturer's cavitation analysis.

NPSH available is calculated using absolute pressure at a reference free surface,
fluid vapor pressure, static liquid elevation relative to the impeller centre,
and suction-line friction loss. NPSHr speed scaling uses a simplified affinity
approximation at the given demand. Manufacturer NPSHr(Q,s) data is required
for real design or operational decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .pump import G, PumpSpec


@dataclass(frozen=True)
class SuctionSpec:
    surface_pressure_abs_kpa: float = 101.325
    vapor_pressure_abs_kpa: float = 2.3
    liquid_level_above_pump_m: float = 0.0
    friction_loss_m: float = 1.5
    npshr_reference_m: float = 3.0
    required_margin_ratio: float = 1.3

    def __post_init__(self) -> None:
        if self.surface_pressure_abs_kpa <= 0 or self.vapor_pressure_abs_kpa < 0:
            raise ValueError("Suction surface pressure must be positive and vapor pressure nonnegative.")
        if self.friction_loss_m < 0 or self.npshr_reference_m <= 0:
            raise ValueError("Suction friction loss must be nonnegative and reference NPSHr positive.")
        if self.required_margin_ratio < 1:
            raise ValueError("The requested NPSH margin ratio must be at least 1.0.")


@dataclass(frozen=True)
class NPSHScreen:
    available_m: float
    required_m: float
    margin_m: float
    margin_ratio: float
    passes_requested_margin: bool


def available_npsh_m(suction: SuctionSpec, density_kg_m3: float) -> float:
    if density_kg_m3 <= 0:
        raise ValueError("Fluid density must be positive.")
    pressure_head = 1000.0 * (suction.surface_pressure_abs_kpa - suction.vapor_pressure_abs_kpa) / (density_kg_m3 * G)
    return pressure_head + suction.liquid_level_above_pump_m - suction.friction_loss_m


def required_npsh_m(suction: SuctionSpec, speed_ratio: float) -> float:
    if speed_ratio <= 0:
        raise ValueError("Speed ratio must be positive.")
    return suction.npshr_reference_m * speed_ratio ** 2


def screen_npsh(suction: SuctionSpec, pump: PumpSpec, speed_ratio: float) -> NPSHScreen:
    available = available_npsh_m(suction, pump.density_kg_m3)
    required = required_npsh_m(suction, speed_ratio)
    ratio = available / required
    return NPSHScreen(available, required, available - required, ratio, ratio >= suction.required_margin_ratio - 1e-12)


def npsh_max_speed_ratio(suction: SuctionSpec, pump: PumpSpec) -> float:
    """Upper speed under the simplified NPSHr~speed² screening assumption.

    A negative or zero available NPSH is not feasible, and is rejected.
    """
    available = available_npsh_m(suction, pump.density_kg_m3)
    if available <= 0:
        raise ValueError("Suction assumptions yield zero or negative NPSH available; no screened speed is feasible.")
    return sqrt(available / (suction.npshr_reference_m * suction.required_margin_ratio))
