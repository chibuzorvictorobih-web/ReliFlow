"""Weibull lifetime model and exact age-replacement renewal-reward calculations.

The policy assumes perfect restoration to 'as new' at planned replacement or
corrective repair, independent identically distributed lifetimes, and constant
outage durations. Replace these assumptions for real plant decision-making.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from scipy.special import gamma, gammainc


@dataclass(frozen=True)
class WeibullSpec:
    shape: float = 2.2
    characteristic_life_hours: float = 10_000.0

    def __post_init__(self) -> None:
        if self.shape <= 0 or self.characteristic_life_hours <= 0:
            raise ValueError("Weibull shape and characteristic life must be positive.")


@dataclass(frozen=True)
class MaintenanceSpec:
    preventive_duration_hours: float = 6.0
    corrective_duration_hours: float = 48.0
    preventive_cost: float = 550.0
    corrective_cost: float = 5_000.0
    downtime_cost_per_hour: float = 650.0

    def __post_init__(self) -> None:
        if any(x < 0 for x in (
            self.preventive_duration_hours, self.corrective_duration_hours,
            self.preventive_cost, self.corrective_cost, self.downtime_cost_per_hour,
        )):
            raise ValueError("Maintenance durations and costs cannot be negative.")


@dataclass(frozen=True)
class MaintenanceMetrics:
    interval_hours: float | None
    survival_at_interval: float
    probability_failure_before_interval: float
    expected_operating_hours_per_cycle: float
    expected_downtime_hours_per_cycle: float
    availability: float
    maintenance_cost_per_calendar_hour: float
    downtime_cost_per_calendar_hour: float


def survival(spec: WeibullSpec, operating_age_hours: float) -> float:
    if operating_age_hours < 0:
        raise ValueError("Operating age cannot be negative.")
    return exp(-((operating_age_hours / spec.characteristic_life_hours) ** spec.shape))


def conditional_survival(spec: WeibullSpec, age_hours: float, future_hours: float) -> float:
    """Probability of surviving future_hours, conditional on survival to age_hours."""
    if age_hours < 0 or future_hours < 0:
        raise ValueError("Age and future period cannot be negative.")
    scale = spec.characteristic_life_hours
    return exp(-(((age_hours + future_hours) / scale) ** spec.shape - (age_hours / scale) ** spec.shape))


def hazard_per_hour(spec: WeibullSpec, age_hours: float) -> float:
    if age_hours <= 0:
        raise ValueError("Use positive operating age for Weibull hazard evaluation.")
    return (spec.shape / spec.characteristic_life_hours) * (
        age_hours / spec.characteristic_life_hours
    ) ** (spec.shape - 1.0)


def mean_lifetime_hours(spec: WeibullSpec) -> float:
    """MTTF of a fresh component, not repairable-system MTBF."""
    return spec.characteristic_life_hours * gamma(1.0 + 1.0 / spec.shape)


def age_replacement(
    lifetime: WeibullSpec, maintenance: MaintenanceSpec, interval_hours: float | None
) -> MaintenanceMetrics:
    """Age-replacement policy in operating hours; None means run to failure.

    E[uptime] = integral(0,T) R(t)dt = η/β Γ(1/β) P(1/β,(T/η)^β).
    Cycle downtime = P(failure)*d_CM + P(PM)*d_PM.
    Cycle maintenance cost is weighted in the same way.
    Calendar-time rates divide expected cost by expected uptime + downtime.
    """
    if interval_hours is not None and interval_hours <= 0:
        raise ValueError("Preventive replacement interval must be positive.")

    if interval_hours is None:
        probability_survive, probability_fail = 0.0, 1.0
        uptime = mean_lifetime_hours(lifetime)
    else:
        beta = lifetime.shape
        eta = lifetime.characteristic_life_hours
        scaled_time = (interval_hours / eta) ** beta
        probability_survive = exp(-scaled_time)
        probability_fail = 1.0 - probability_survive
        uptime = eta / beta * gamma(1.0 / beta) * gammainc(1.0 / beta, scaled_time)

    downtime = (
        probability_survive * maintenance.preventive_duration_hours
        + probability_fail * maintenance.corrective_duration_hours
    )
    calendar_cycle = uptime + downtime
    if calendar_cycle <= 0:
        raise ValueError("The assumed renewal cycle has no calendar duration.")
    cycle_maintenance_cost = (
        probability_survive * maintenance.preventive_cost
        + probability_fail * maintenance.corrective_cost
    )
    return MaintenanceMetrics(
        interval_hours=interval_hours,
        survival_at_interval=probability_survive,
        probability_failure_before_interval=probability_fail,
        expected_operating_hours_per_cycle=uptime,
        expected_downtime_hours_per_cycle=downtime,
        availability=uptime / calendar_cycle,
        maintenance_cost_per_calendar_hour=cycle_maintenance_cost / calendar_cycle,
        downtime_cost_per_calendar_hour=(downtime / calendar_cycle)
        * maintenance.downtime_cost_per_hour,
    )
