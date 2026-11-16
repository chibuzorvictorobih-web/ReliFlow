"""Regression checks for new diagnostics, independent of the UI."""
from io import BytesIO

import pytest
from pypdf import PdfReader

from reliflow.pump import PumpSpec, SystemSpec, system_head_m
from reliflow.optimization import EconomicsSpec, evaluate_strategy, optimize_strategy
from reliflow.reliability import WeibullSpec, MaintenanceSpec
from reliflow.parallel import parallel_duty, best_parallel_energy
from reliflow.robustness import reliability_sensitivity
from reliflow.suction import SuctionSpec, available_npsh_m, screen_npsh, npsh_max_speed_ratio
from reliflow.report import make_report_pdf
from reliflow import __version__

PUMP = PumpSpec()
SYSTEM = SystemSpec()
LIFE = WeibullSpec()
MAINT = MaintenanceSpec()
ECON = EconomicsSpec()


def test_version_unchanged():
    assert __version__ == "1.1.0"


def test_npsh_available_manual_pressure_head():
    params = SuctionSpec(101.325, 2.3, 0, 1.5, 3, 1.3)
    head = (101.325 - 2.3) * 1000 / (PUMP.density_kg_m3 * 9.80665) - 1.5
    assert available_npsh_m(params, PUMP.density_kg_m3) == pytest.approx(head)


def test_npsh_speed_screen_margin():
    settings = SuctionSpec()
    limit = npsh_max_speed_ratio(settings, PUMP)
    assert screen_npsh(settings, PUMP, limit).margin_ratio == pytest.approx(settings.required_margin_ratio)
    assert screen_npsh(settings, PUMP, limit * 1.01).passes_requested_margin is False


@pytest.mark.parametrize("invalid", [
    {"surface_pressure_abs_kpa": 0},
    {"vapor_pressure_abs_kpa": -1},
    {"friction_loss_m": -1},
    {"npshr_reference_m": 0},
    {"required_margin_ratio": 0.8},
])
def test_npsh_input_validation(invalid):
    with pytest.raises(ValueError):
        SuctionSpec(**invalid)


def test_npsh_negative_available_raises():
    s = SuctionSpec(surface_pressure_abs_kpa=50, vapor_pressure_abs_kpa=51)
    with pytest.raises(ValueError):
        npsh_max_speed_ratio(s, PUMP)


def test_parallel_energy_and_shared_system_head():
    result = parallel_duty(PUMP, SYSTEM, 70, 2, 1.0)
    assert result.per_pump_duty.flow_m3h == pytest.approx(35)
    assert result.per_pump_duty.system_head_m == pytest.approx(system_head_m(SYSTEM, 70))
    assert result.combined_electric_kw == pytest.approx(2 * result.per_pump_duty.electric_power_kw)
    assert result.specific_energy_kwh_m3 == pytest.approx(result.combined_electric_kw / 70)


def test_parallel_one_pump_matches_original_duty():
    from reliflow.pump import controlled_duty
    expected = controlled_duty(PUMP, SYSTEM, 70, 1.0)
    actual = parallel_duty(PUMP, SYSTEM, 70, 1, 1.0)
    assert actual.combined_electric_kw == pytest.approx(expected.electric_power_kw)


@pytest.mark.parametrize("count", [0, -1, 11, 1.5])
def test_parallel_rejects_invalid_count(count):
    with pytest.raises(ValueError):
        parallel_duty(PUMP, SYSTEM, 70, count, 1.0)


def test_parallel_best_speed_satisfies_hydraulics():
    result = best_parallel_energy(PUMP, SYSTEM, 70, 2, 0.65, 1.15)
    assert 0.65 <= result.speed_ratio <= 1.15
    assert result.per_pump_duty.throttling_head_m >= 0
    assert result.combined_electric_kw <= parallel_duty(PUMP, SYSTEM, 70, 2, 1.0).combined_electric_kw


def test_parallel_rejects_capacity_failure():
    with pytest.raises(ValueError):
        best_parallel_energy(PUMP, SYSTEM, 70, 1, 0.2, 0.3)


def test_uncertainty_central_reproduces_optimized_result():
    opt = optimize_strategy(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, 0.65, 1.15, 500, 25000)
    base = evaluate_strategy(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, 1.0, 7500)
    rows = reliability_sensitivity(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, opt, 0.15, 0.20, base)
    assert len(rows) == 9
    assert rows[4]["Annual cost ($)"] == pytest.approx(opt.annual_total_cost, abs=0.01)
    assert rows[4]["Cost difference vs baseline ($)"] == pytest.approx(base.annual_total_cost - opt.annual_total_cost, abs=0.01)
    assert len({row["Annual cost ($)"] for row in rows}) > 1


def test_uncertainty_rejects_negative_fraction():
    opt = optimize_strategy(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, 0.65, 1.15, 500, 25000)
    with pytest.raises(ValueError):
        reliability_sensitivity(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, opt, -0.1)


def test_report_contains_valid_summary_pdf():
    opt = optimize_strategy(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, 0.65, 1.15, 500, 25000)
    base = evaluate_strategy(PUMP, SYSTEM, 70, LIFE, MAINT, ECON, 1.0, 7500)
    settings = SuctionSpec()
    pdf = make_report_pdf("Illustrative cooling-water circuit", __version__, 70, opt, base,
                          settings, screen_npsh(settings, PUMP, opt.duty.speed_ratio))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    reader = PdfReader(BytesIO(pdf))
    assert 1 <= len(reader.pages) <= 3
    text = " ".join(p.extract_text() for p in reader.pages)
    assert "ReliFlow" in text and "Version: 1.1.0" in text
    assert "NPSH" in text and "Annual total cost" in text
