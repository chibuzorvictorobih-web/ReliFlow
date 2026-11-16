"""Closed-form NIST Weibull and renewal-reward validation."""

import math

import pytest

from reliflow.reliability import (
    MaintenanceSpec, WeibullSpec, age_replacement, conditional_survival,
    hazard_per_hour, mean_lifetime_hours, survival,
)


def test_exponential_weibull_mean_and_survival():
    spec = WeibullSpec(shape=1.0, characteristic_life_hours=1000.0)
    assert mean_lifetime_hours(spec) == pytest.approx(1000.0)
    assert survival(spec, 1000.0) == pytest.approx(math.exp(-1.0))
    assert hazard_per_hour(spec, 100) == pytest.approx(0.001)


def test_weibull_mean_shape_2():
    spec = WeibullSpec(shape=2.0, characteristic_life_hours=1000.0)
    assert mean_lifetime_hours(spec) == pytest.approx(1000 * math.sqrt(math.pi) / 2)


def test_conditional_reliability_formula():
    spec = WeibullSpec(shape=2, characteristic_life_hours=1000)
    actual = conditional_survival(spec, 200, 300)
    assert actual == pytest.approx(survival(spec, 500) / survival(spec, 200))
    assert conditional_survival(spec, 0, 300) == pytest.approx(survival(spec, 300))


def test_age_replacement_exponential_integral():
    lifetime = WeibullSpec(1, 1000)
    maintenance = MaintenanceSpec(preventive_duration_hours=3, corrective_duration_hours=10,
                                  preventive_cost=10, corrective_cost=100, downtime_cost_per_hour=250)
    interval = 500
    result = age_replacement(lifetime, maintenance, interval)
    survive = math.exp(-0.5)
    uptime = 1000 * (1 - survive)
    downtime = survive * 3 + (1 - survive) * 10
    assert result.expected_operating_hours_per_cycle == pytest.approx(uptime)
    assert result.expected_downtime_hours_per_cycle == pytest.approx(downtime)
    assert result.availability == pytest.approx(uptime / (uptime + downtime))
    assert result.maintenance_cost_per_calendar_hour == pytest.approx(
        (survive * 10 + (1 - survive) * 100) / (uptime + downtime)
    )
    assert result.downtime_cost_per_calendar_hour == pytest.approx(
        250 * downtime / (uptime + downtime)
    )


def test_run_to_failure_is_exact_mean_life_renewal():
    lifetime, maintenance = WeibullSpec(), MaintenanceSpec()
    result = age_replacement(lifetime, maintenance, None)
    mttf = mean_lifetime_hours(lifetime)
    assert result.probability_failure_before_interval == 1.0
    assert result.survival_at_interval == 0
    assert result.expected_operating_hours_per_cycle == pytest.approx(mttf)
    assert result.availability == pytest.approx(mttf / (mttf + maintenance.corrective_duration_hours))


def test_large_pm_interval_converges_to_run_to_failure():
    lifetime, maintenance = WeibullSpec(), MaintenanceSpec()
    result = age_replacement(lifetime, maintenance, 500000)
    run_to_failure = age_replacement(lifetime, maintenance, None)
    assert result.availability == pytest.approx(run_to_failure.availability, rel=1e-10)


def test_invalid_age_and_costs():
    with pytest.raises(ValueError):
        survival(WeibullSpec(), -1)
    with pytest.raises(ValueError):
        age_replacement(WeibullSpec(), MaintenanceSpec(), 0)
    with pytest.raises(ValueError):
        MaintenanceSpec(corrective_cost=-2)
    with pytest.raises(ValueError):
        WeibullSpec(shape=0)
