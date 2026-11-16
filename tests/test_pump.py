"""Analytical hydraulics checks and invalid-duty guards."""

import math

import pytest

from reliflow.pump import (
    PumpSpec, SystemSpec, controlled_duty, free_flow_point, minimum_feasible_speed,
    pump_head_m, system_head_m,
)


def test_affinity_law_at_corresponding_flow():
    p = PumpSpec()
    flow = 64.0
    ratio = 0.81
    assert pump_head_m(p, flow * ratio, ratio) == pytest.approx(
        ratio**2 * pump_head_m(p, flow, 1.0)
    )


def test_natural_operating_point_is_curve_intersection():
    p, sys = PumpSpec(), SystemSpec()
    flow, head = free_flow_point(p, sys, 1.0)
    assert head == pytest.approx(pump_head_m(p, flow, 1.0), abs=1e-8)
    assert head == pytest.approx(system_head_m(sys, flow), abs=1e-8)


def test_zero_natural_flow_when_static_head_exceeds_shutoff():
    assert free_flow_point(PumpSpec(), SystemSpec(static_head_m=100), 1.0) is None


def test_minimum_feasible_speed_satisfies_system_head():
    p, sys, q = PumpSpec(), SystemSpec(), 70.0
    minimum = minimum_feasible_speed(p, sys, q)
    assert pump_head_m(p, q, minimum) == pytest.approx(system_head_m(sys, q))
    duty = controlled_duty(p, sys, q, minimum)
    assert duty.throttling_head_m == pytest.approx(0, abs=1e-8)


def test_power_calculation_has_correct_hour_to_second_conversion():
    p, sys = PumpSpec(), SystemSpec()
    duty = controlled_duty(p, sys, 70.0, 1.0)
    expected = (
        p.density_kg_m3 * 9.80665 * (70 / 3600) * duty.pump_head_m
        / 1000 / (duty.pump_efficiency * p.motor_efficiency * p.drive_efficiency)
    )
    assert duty.electric_power_kw == pytest.approx(expected)
    assert duty.specific_energy_kwh_m3 == pytest.approx(expected / 70)


def test_lower_speed_reduces_power_for_same_delivered_flow_example():
    p, sys = PumpSpec(), SystemSpec()
    full = controlled_duty(p, sys, 70, 1)
    optimal_feasible_speed = minimum_feasible_speed(p, sys, 70)
    variable = controlled_duty(p, sys, 70, optimal_feasible_speed)
    assert variable.flow_m3h == full.flow_m3h
    assert variable.electric_power_kw < full.electric_power_kw
    assert full.throttling_head_m > 0


def test_infeasible_speed_is_rejected():
    with pytest.raises(ValueError, match="Minimum theoretical feasible speed"):
        controlled_duty(PumpSpec(), SystemSpec(), 70, 0.6)


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        PumpSpec(bep_efficiency=1.2)
    with pytest.raises(ValueError):
        PumpSpec(shutoff_head_m=0)
    with pytest.raises(ValueError):
        SystemSpec(static_head_m=-1)
    with pytest.raises(ValueError):
        minimum_feasible_speed(PumpSpec(), SystemSpec(), 0)
