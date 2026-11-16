"""Optimizer feasibility, accounting identities, and case-study regression."""

import pytest

from reliflow.optimization import EconomicsSpec, evaluate_strategy, optimize_strategy
from reliflow.pump import PumpSpec, SystemSpec, minimum_feasible_speed
from reliflow.reliability import MaintenanceSpec, WeibullSpec


@pytest.fixture
def scenario():
    return PumpSpec(), SystemSpec(), 70.0, WeibullSpec(), MaintenanceSpec(), EconomicsSpec()


def test_economics_costs_and_annual_volume_are_consistent(scenario):
    p, s, q, life, maint, econ = scenario
    res = evaluate_strategy(p, s, q, life, maint, econ, 1.0, 7500.0)
    assert res.annual_uptime_hours == pytest.approx(econ.annual_scheduled_hours * res.maintenance.availability)
    assert res.expected_annual_volume_m3 == pytest.approx(res.annual_uptime_hours * q)
    assert res.annual_electricity_kwh == pytest.approx(res.annual_uptime_hours * res.duty.electric_power_kw)
    assert res.annual_energy_cost == pytest.approx(res.annual_electricity_kwh * econ.electricity_price_per_kwh)
    assert res.annual_emissions_kgco2 == pytest.approx(res.annual_electricity_kwh * econ.grid_emissions_kgco2_per_kwh)
    assert res.annual_total_cost == pytest.approx(res.annual_energy_cost + res.annual_maintenance_cost + res.annual_downtime_cost)


def test_optimal_is_feasible_and_beats_example_baseline(scenario):
    p, s, q, life, maint, econ = scenario
    result = optimize_strategy(p, s, q, life, maint, econ, 0.65, 1.15, 500, 25000)
    baseline = evaluate_strategy(p, s, q, life, maint, econ, 1.0, 7500)
    assert 0.65 <= result.duty.speed_ratio <= 1.15
    assert result.duty.speed_ratio >= minimum_feasible_speed(p, s, q) - 1e-12
    assert result.annual_total_cost <= baseline.annual_total_cost
    assert result.duty.flow_m3h == baseline.duty.flow_m3h
    assert result.duty.specific_energy_kwh_m3 <= baseline.duty.specific_energy_kwh_m3
    assert 0 < result.maintenance.availability <= 1


def test_optimizer_catches_infeasible_search_range(scenario):
    p, s, q, life, maint, econ = scenario
    with pytest.raises(ValueError, match="No speed"):
        optimize_strategy(p, s, q, life, maint, econ, 0.5, 0.7, 500, 25000)


def test_optimizer_can_choose_run_to_failure_when_preventive_is_expensive(scenario):
    p, s, q, life, _, econ = scenario
    # Exponential failures + identical repair duration: scheduled PM wastes money.
    life = WeibullSpec(shape=1, characteristic_life_hours=12000)
    maint = MaintenanceSpec(preventive_duration_hours=48, corrective_duration_hours=48,
                            preventive_cost=999999, corrective_cost=10, downtime_cost_per_hour=0)
    result = optimize_strategy(p, s, q, life, maint, econ, 0.65, 1.15, 100, 25000)
    assert result.maintenance.interval_hours is None


def test_invalid_objective_inputs():
    with pytest.raises(ValueError):
        EconomicsSpec(annual_scheduled_hours=-10)
    with pytest.raises(ValueError):
        EconomicsSpec(electricity_price_per_kwh=-1)
