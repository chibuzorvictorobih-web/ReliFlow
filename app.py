"""ReliFlow — interactive, defensible pump-energy and maintenance optimization.

To run locally: streamlit run app.py
All values are synthetic examples by default. No private plant information.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from reliflow import __version__
from reliflow.optimization import EconomicsSpec, evaluate_strategy, optimize_strategy
from reliflow.presets import PRESETS
from reliflow.pump import (
    PumpSpec, SystemSpec, controlled_duty, free_flow_point,
    minimum_feasible_speed, pump_head_m, system_head_m,
)
from reliflow.reliability import (
    WeibullSpec, MaintenanceSpec, age_replacement, conditional_survival,
    hazard_per_hour, mean_lifetime_hours, survival,
)

st.set_page_config(page_title="ReliFlow | Reliability & Energy", page_icon="⚙️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.45rem; padding-bottom: 3rem; max-width: 1350px;}
[data-testid="stMetric"] {
    background: #172638;
    border: 1px solid #35465B;
    padding: 1rem;
    border-radius: 0.75rem;
    box-shadow: none;
}
[data-testid="stMetricLabel"], [data-testid="stMetricDelta"] {
    color: #B9C8D9 !important;
}
[data-testid="stMetricValue"] {
    color: #F8FAFC !important;
}
.small-note {color:#B9C8D9; font-size:0.92rem;}
</style>
""", unsafe_allow_html=True)


def number(label: str, source: dict, name: str, *, min_value: float = 0.0,
           max_value: float | None = None, step: float = 1.0, fmt: str = "%.2f") -> float:
    """Scenario-specific keys mean switching presets resets inputs predictably."""
    # Streamlit requires value, min_value, max_value and step to share one
    # numeric type. Percentage limits such as 20 and 140 are passed as ints
    # by callers, so normalize everything to float at the widget boundary.
    return float(st.number_input(
        label,
        min_value=None if min_value is None else float(min_value),
        max_value=None if max_value is None else float(max_value),
        value=float(source[name]),
        step=float(step),
        format=fmt,
        key=f"{st.session_state['preset_name']}:{name}",
    ))


def money(x: float) -> str:
    return f"${x:,.0f}"


def format_interval(interval: float | None) -> str:
    return "Run to failure" if interval is None else f"{interval:,.0f} operating h"


def plot_style(fig: go.Figure, title: str, x_label: str, y_label: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=17)),
        xaxis_title=x_label, yaxis_title=y_label,
        margin=dict(l=20, r=20, t=65, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E7EDEF", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E7EDEF", zeroline=False)
    return fig


def make_sensitivity(pump, system, flow, lifetime, maintenance, econ, low_speed, high_speed, low_pm, high_pm):
    """Human-readable CSV rows with one speed and PM policy per row."""
    start = max(low_speed, minimum_feasible_speed(pump, system, flow))
    speeds = np.linspace(start, high_speed, 25)
    intervals = list(np.geomspace(low_pm, high_pm, 35)) + [None]
    rows = []
    for speed in speeds:
        for interval in intervals:
            result = evaluate_strategy(pump, system, flow, lifetime, maintenance, econ, float(speed), interval)
            rows.append({
                "speed_percent": round(100 * float(speed), 3),
                "replacement_interval_operating_hours": "run_to_failure" if interval is None else round(float(interval), 2),
                "pump_electrical_kw": round(result.duty.electric_power_kw, 4),
                "specific_energy_kwh_per_m3": round(result.duty.specific_energy_kwh_m3, 6),
                "availability_percent": round(100 * result.maintenance.availability, 4),
                "expected_annual_volume_m3": round(result.expected_annual_volume_m3, 2),
                "annual_energy_cost_currency_units": round(result.annual_energy_cost, 2),
                "annual_maintenance_cost_currency_units": round(result.annual_maintenance_cost, 2),
                "annual_downtime_cost_currency_units": round(result.annual_downtime_cost, 2),
                "annual_total_cost_currency_units": round(result.annual_total_cost, 2),
            })
    return pd.DataFrame(rows)


# --- User-editable transparent scenario. ---
with st.sidebar:
    st.title("⚙️ Model settings")
    preset_name = st.selectbox("Illustrative scenario", list(PRESETS), key="preset_name")
    seed = PRESETS[preset_name]
    st.caption("Examples are synthetic, not measured refinery operating data.")

    # Forms stop the expensive optimizer from running after every input edit.
    # Changing a preset happens outside the form, so each preset gets its own defaults.
    with st.form("reliflow_calculator_form", border=False):
        with st.expander("1 · Pump curve and system", expanded=True):
            shutoff = number("Shutoff head at reference speed (m)", seed, "shutoff_head_m", min_value=1.0)
            curve = number("Pump curve a [m/(m³/h)²]", seed, "head_curve_coefficient", min_value=0.000001, step=0.0001, fmt="%.5f")
            static_head = number("Static head (m)", seed, "static_head_m")
            resistance = number("System curve k [m/(m³/h)²]", seed, "resistance_coefficient", step=0.0001, fmt="%.5f")
            bep_flow = number("Reference BEP flow (m³/h)", seed, "bep_flow_m3h", min_value=1.0)
            bep_eta = number("BEP efficiency (0–1)", seed, "bep_efficiency", min_value=0.05, max_value=1.0, step=0.01)
            eta_penalty = number("Off-BEP efficiency curvature", seed, "efficiency_penalty", step=0.01)
            motor_eta = number("Motor efficiency (0–1)", seed, "motor_efficiency", min_value=0.05, max_value=1.0, step=0.01)
            drive_eta = number("VSD efficiency (0–1)", seed, "drive_efficiency", min_value=0.05, max_value=1.0, step=0.01)
            density = number("Fluid density (kg/m³)", seed, "density_kg_m3", min_value=1.0)

        with st.expander("2 · Duty and operating speed", expanded=True):
            flow = number("Required delivered flow (m³/h)", seed, "required_flow_m3h", min_value=1.0)
            selected_speed = st.slider(
                "Displayed speed (% of reference)", min_value=50, max_value=125,
                value=int(seed["selected_speed_percent"]), step=1, key=f"{preset_name}:selected_speed",
            ) / 100.0
            min_speed = number("Minimum allowable optimization speed (%)", seed, "min_speed_percent", min_value=20, max_value=140, step=1.0, fmt="%.0f") / 100.0
            max_speed = number("Maximum allowable optimization speed (%)", seed, "max_speed_percent", min_value=20, max_value=140, step=1.0, fmt="%.0f") / 100.0

        with st.expander("3 · Failure and preventive maintenance"):
            beta = number("Weibull shape β", seed, "shape", min_value=0.2, max_value=10.0, step=0.1)
            eta = number("Characteristic life η (operating hours)", seed, "characteristic_life_hours", min_value=10.0)
            d_pm = number("Planned replacement downtime (h)", seed, "preventive_duration_hours")
            d_cm = number("Failure repair downtime (h)", seed, "corrective_duration_hours")
            c_pm = number("Planned replacement cost ($)", seed, "preventive_cost")
            c_cm = number("Failure repair cost ($)", seed, "corrective_cost")
            c_out = number("Value of unserved time ($/h)", seed, "downtime_cost_per_hour")
            baseline_run = st.checkbox("Run to failure as baseline", value=False, key=f"{preset_name}:baseline_run")
            baseline_pm = None if baseline_run else number("Baseline replacement interval (operating h)", seed, "baseline_pm_interval", min_value=10.0)
            low_pm = number("Shortest PM interval in search (h)", seed, "pm_min_hours", min_value=1.0)
            high_pm = number("Longest PM interval in search (h)", seed, "pm_max_hours", min_value=1.0)
            age = number("Current survived operating age (h)", seed, "current_age_hours")
            horizon = number("Future reliability horizon (h)", seed, "future_horizon_hours")

        with st.expander("4 · Energy and environmental assumptions"):
            annual_hours = number("Scheduled operation (calendar h/year)", seed, "annual_scheduled_hours", min_value=1.0, max_value=8784.0)
            energy_price = number("Electricity price ($/kWh)", seed, "electricity_price_per_kwh", step=0.01)
            grid_factor = number("Emission factor (kg CO₂/kWh)", seed, "grid_emissions_kgco2_per_kwh", step=0.01)

        st.caption("Costs use example $ units. You may interpret them in another consistent currency by changing values.")


        submitted = st.form_submit_button(
            "🧮 Calculate & Optimize", type="primary", use_container_width=True
        )

# Run the model only when the user explicitly presses Calculate & Optimize.
# Keep the last submitted results in session state, including when a download
# widget triggers a Streamlit rerun. An unsubmitted preset never shows results
# computed for a different scenario.
if submitted:
    try:
        with st.spinner("Calculating hydraulics, reliability and optimal maintenance…"):
            pump = PumpSpec(shutoff, curve, bep_flow, bep_eta, eta_penalty, motor_eta, drive_eta, density)
            system = SystemSpec(static_head, resistance)
            lifetime = WeibullSpec(beta, eta)
            maintenance = MaintenanceSpec(d_pm, d_cm, c_pm, c_cm, c_out)
            economics = EconomicsSpec(annual_hours, energy_price, grid_factor)
            if min_speed > max_speed or low_pm > high_pm:
                raise ValueError("Optimization search bounds must increase from minimum to maximum.")
            optimized = optimize_strategy(pump, system, flow, lifetime, maintenance, economics,
                                          min_speed, max_speed, low_pm, high_pm)
            baseline = None
            try:
                baseline = evaluate_strategy(pump, system, flow, lifetime, maintenance, economics,
                                             1.0, baseline_pm)
            except ValueError:
                pass
            chosen = None
            try:
                chosen = evaluate_strategy(pump, system, flow, lifetime, maintenance, economics,
                                           selected_speed, baseline_pm)
            except ValueError:
                pass
            st.session_state["reliflow_last_result"] = {
                "preset": preset_name,
                "model": (pump, system, lifetime, maintenance, economics),
                "strategies": (optimized, baseline, chosen),
                "inputs": {
                    "flow": flow, "selected_speed": selected_speed,
                    "min_speed": min_speed, "max_speed": max_speed,
                    "low_pm": low_pm, "high_pm": high_pm,
                    "age": age, "horizon": horizon, "eta": eta,
                    "grid_factor": grid_factor, "baseline_pm": baseline_pm,
                },
            }
            st.session_state.pop("reliflow_last_error", None)
    except (ValueError, OverflowError) as exc:
        st.session_state.pop("reliflow_last_result", None)
        st.session_state["reliflow_last_error"] = {"preset": preset_name, "message": str(exc)}

st.title("ReliFlow")
st.markdown("**Industrial Equipment Reliability & Energy Optimization**")
st.caption(f"Version {__version__} · A reproducible educational engineering case study · All default inputs are illustrative")

analysis = st.session_state.get("reliflow_last_result")
if analysis is None or analysis["preset"] != preset_name:
    last_error = st.session_state.get("reliflow_last_error")
    if last_error and last_error["preset"] == preset_name:
        st.error(f"Please adjust the model inputs: {last_error['message']}")
    st.info("Select an illustrative scenario, edit the sidebar parameters, then press "
            "**🧮 Calculate & Optimize** to generate pump, reliability, energy and maintenance results.")
    st.stop()

pump, system, lifetime, maintenance, economics = analysis["model"]
optimized, baseline, chosen = analysis["strategies"]
active = analysis["inputs"]
flow, selected_speed = active["flow"], active["selected_speed"]
min_speed, max_speed = active["min_speed"], active["max_speed"]
low_pm, high_pm = active["low_pm"], active["high_pm"]
age, horizon, eta = active["age"], active["horizon"], active["eta"]
grid_factor, baseline_pm = active["grid_factor"], active["baseline_pm"]
st.caption("Showing the **last calculated** results. Changes in the sidebar take effect only after you press Calculate & Optimize again.")
st.info("The model satisfies the SAME required flow in all feasible control scenarios by assuming a throttling valve absorbs excess head. "
        "Speed changes do not automatically alter failure rates in this model.", icon="ℹ️")

if chosen is None:
    st.warning(f"The selected display speed of {selected_speed:.0%} cannot supply the requested flow. "
               f"The minimum feasible speed is {minimum_feasible_speed(pump, system, flow):.1%}. "
               "The optimizer still evaluates permitted feasible speeds.")
if baseline is None:
    st.warning("The nominal 100% speed reference cannot supply the specified required flow, so baseline savings are not reported.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Optimized speed", f"{optimized.duty.speed_ratio:.1%} reference")
m2.metric("Recommended maintenance", format_interval(optimized.maintenance.interval_hours))
m3.metric("Expected availability", f"{optimized.maintenance.availability:.2%}")
m4.metric("Estimated annual total cost", money(optimized.annual_total_cost))


overview, hydraulics, reliability, decision, methods = st.tabs([
    "Overview", "Pump & energy", "Reliability", "Optimization & exports", "Methods & limitations"
])

with overview:
    st.subheader("Engineering decision at a glance")
    a, b = st.columns([1.15, 1])
    with a:
        st.markdown("**Optimum within the configured search bounds**")
        st.write(
            f"Operate at approximately **{optimized.duty.speed_ratio:.1%} of reference speed** "
            f"to deliver **{flow:,.1f} m³/h**; use **{format_interval(optimized.maintenance.interval_hours)}** "
            f"for the age-replacement policy. Modelled duty electricity is "
            f"**{optimized.duty.electric_power_kw:.2f} kW** and the predicted annual "
            f"production is **{optimized.expected_annual_volume_m3:,.0f} m³** after availability effects."
        )
        st.markdown("**Optimization objective**")
        st.latex(r"\min_{s,T}\; C_{\mathrm{energy}}(s,T)+C_{\mathrm{maintenance}}(T)+C_{\mathrm{outage}}(T)")
        st.caption("A finite, transparent search is used rather than a claim of continuous global optimality.")
        if optimized.maintenance.interval_hours is not None:
            if (abs(optimized.maintenance.interval_hours - low_pm) < 1e-6 or
                    abs(optimized.maintenance.interval_hours - high_pm) < 1e-6):
                st.warning("The optimal preventive interval is at a search boundary; widen the permitted PM range to test robustness.")
        if abs(optimized.duty.speed_ratio - max_speed) < 1e-9:
            st.warning("The best speed sits on the maximum allowed bound; review pump capacity and control limits.")
    with b:
        comparison = [
            ("Baseline @ 100%", baseline),
            ("Selected", chosen),
            ("Optimized", optimized),
        ]
        rows = []
        for name, obj in comparison:
            if obj is not None:
                rows.append({
                    "Strategy": name,
                    "Speed": f"{obj.duty.speed_ratio:.1%}",
                    "Pump input (kW)": round(obj.duty.electric_power_kw, 2),
                    "kWh/m³": round(obj.duty.specific_energy_kwh_m3, 4),
                    "Availability": f"{obj.maintenance.availability:.2%}",
                    "Annual cost ($)": round(obj.annual_total_cost),
                })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if baseline is not None:
            specific_saved = 100 * (
                baseline.duty.specific_energy_kwh_m3 - optimized.duty.specific_energy_kwh_m3
            ) / baseline.duty.specific_energy_kwh_m3
            total_saved = baseline.annual_total_cost - optimized.annual_total_cost
            st.metric("Electricity per m³ reduction vs 100% speed", f"{specific_saved:.1f}%")
            st.metric("Annual modeled cost difference vs baseline", money(total_saved))
            st.caption("Same delivered flow rate; baseline and optimized availability can differ. "
                       "Annual total cost includes the assumed monetary value of outages.")

    st.divider()
    st.subheader("Annual cost breakdown")
    figure = go.Figure()
    available_results = [("Baseline", baseline), ("Selected", chosen), ("Optimized", optimized)]
    available_results = [(name, res) for name, res in available_results if res is not None]
    for name, attr, color in [
        ("Energy", "annual_energy_cost", "#0E8E83"),
        ("Maintenance", "annual_maintenance_cost", "#428CB4"),
        ("Unserved-time penalty", "annual_downtime_cost", "#D99643"),
    ]:
        figure.add_bar(name=name, x=[key for key, _ in available_results],
                       y=[getattr(res, attr) for _, res in available_results], marker_color=color)
    figure.update_layout(barmode="stack", yaxis_title="Illustrative annual cost ($)",
                         margin=dict(t=18, b=20, l=15, r=15),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(figure, use_container_width=True)

with hydraulics:
    st.subheader("Centrifugal-pump curves and controlled duty")
    max_plot_flow = max(flow * 1.6, bep_flow * max(1.3, max_speed * 1.4))
    q = np.linspace(0, max_plot_flow, 300)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=q, y=[system_head_m(system, float(z)) for z in q],
                             mode="lines", name="System curve", line=dict(color="#D99643", width=3)))
    speeds_to_plot = [(1.0, "Reference 100%", "#426C94")]
    if abs(selected_speed - 1.0) > 1e-6:
        speeds_to_plot.append((selected_speed, f"Selected {selected_speed:.0%}", "#9F7CC5"))
    if all(abs(optimized.duty.speed_ratio - sp) > 1e-6 for sp, _, _ in speeds_to_plot):
        speeds_to_plot.append((optimized.duty.speed_ratio, f"Optimal {optimized.duty.speed_ratio:.1%}", "#0C8C80"))
    for speed, name, color in speeds_to_plot:
        hp = [max(0, pump_head_m(pump, float(z), speed)) for z in q]
        hp = [v if v > 0 else None for v in hp]
        fig.add_trace(go.Scatter(x=q, y=hp, mode="lines", name=name, line=dict(color=color, width=2)))
        intersection = free_flow_point(pump, system, speed)
        if intersection is not None:
            fig.add_trace(go.Scatter(x=[intersection[0]], y=[intersection[1]],
                                     mode="markers", name=f"Open-valve duty ({speed:.0%})",
                                     marker=dict(color=color, size=9, symbol="circle")))
    fig.add_trace(go.Scatter(x=[flow], y=[optimized.duty.pump_head_m],
                             mode="markers", name="Optimized controlled duty",
                             marker=dict(color="#074B45", size=13, symbol="diamond")))
    fig.add_vline(x=flow, line_dash="dot", line_color="#727C80")
    st.plotly_chart(plot_style(fig, "Pump–system operating points", "Volumetric flow (m³/h)", "Head (m)"),
                    use_container_width=True)
    st.caption("Open-valve markers show the unthrottled intersection. Controlled-duty markers use the fixed required "
               "flow; the control valve absorbs surplus head. Negative model head is not plotted.")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Required system head", f"{optimized.duty.system_head_m:.2f} m")
    r2.metric("Available pump head", f"{optimized.duty.pump_head_m:.2f} m")
    r3.metric("Excess throttle head", f"{optimized.duty.throttling_head_m:.2f} m")
    r4.metric("Model pump efficiency", f"{optimized.duty.pump_efficiency:.1%}")
    st.markdown("#### Power and specific energy across feasible speeds")
    s_min = max(min_speed, minimum_feasible_speed(pump, system, flow))
    scan_speeds = np.linspace(s_min, max_speed, 120)
    scan = [controlled_duty(pump, system, flow, float(s)) for s in scan_speeds]
    sweep = pd.DataFrame({
        "Speed (% reference)": scan_speeds * 100,
        "Electrical input (kW)": [v.electric_power_kw for v in scan],
        "Specific energy (kWh/m³)": [v.specific_energy_kwh_m3 for v in scan],
    })
    energy_fig = go.Figure()
    energy_fig.add_trace(go.Scatter(x=sweep["Speed (% reference)"],
                                    y=sweep["Specific energy (kWh/m³)"], mode="lines",
                                    line=dict(color="#0C8C80", width=3), name="Specific energy"))
    energy_fig.add_vline(x=optimized.duty.speed_ratio * 100, line_dash="dash", line_color="#D99643")
    st.plotly_chart(plot_style(energy_fig, "Same-flow electricity intensity", "Reference speed (%)", "kWh/m³"),
                    use_container_width=True)

with reliability:
    st.subheader("Weibull survival and maintenance renewal model")
    p_future = conditional_survival(lifetime, age, horizon)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mean fresh-component life (MTTF)", f"{mean_lifetime_hours(lifetime):,.0f} h")
    m2.metric("Survival to current age", f"{survival(lifetime, age):.1%}")
    m3.metric(f"Next {horizon:,.0f} h survival | age {age:,.0f}", f"{p_future:.1%}")
    m4.metric("Optimized expected availability", f"{optimized.maintenance.availability:.2%}")
    st.caption("Conditional survival assumes the component has already survived to the entered operating age. "
               "It is separate from the renewal policy, which resets age after repair/replacement.")
    a, b = st.columns(2)
    t = np.linspace(0, max(1.7 * eta, age + horizon, high_pm), 240)
    fig_survive = go.Figure()
    fig_survive.add_trace(go.Scatter(x=t, y=[100 * survival(lifetime, float(z)) for z in t],
                                    name="Reliability", line=dict(color="#0C8C80", width=3)))
    fig_survive.add_vline(x=age, line_dash="dot", line_color="#D99643")
    a.plotly_chart(plot_style(fig_survive, "Survival of new equipment", "Operating age (h)", "R(t) (%)"),
                   use_container_width=True)
    t_hazard = np.linspace(max(1.0, 0.001 * eta), max(1.7 * eta, age + horizon), 240)
    fig_hazard = go.Figure()
    fig_hazard.add_trace(go.Scatter(x=t_hazard, y=[hazard_per_hour(lifetime, float(z)) * 1000 for z in t_hazard],
                                   name="Instantaneous hazard", line=dict(color="#428CB4", width=3)))
    b.plotly_chart(plot_style(fig_hazard, "Instantaneous failure hazard", "Operating age (h)", "Hazard per 1,000 h"),
                   use_container_width=True)
    policy_x = np.geomspace(low_pm, high_pm, 160)
    policy_list = [age_replacement(lifetime, maintenance, float(value)) for value in policy_x]
    avail_plot = go.Figure()
    avail_plot.add_trace(go.Scatter(x=policy_x, y=[100 * obj.availability for obj in policy_list],
                                    name="Availability", line=dict(color="#0C8C80", width=3)))
    avail_plot.add_hline(y=100 * age_replacement(lifetime, maintenance, None).availability,
                          line_dash="dot", line_color="#9F7CC5", annotation_text="Run to failure")
    if optimized.maintenance.interval_hours is not None:
        avail_plot.add_vline(x=optimized.maintenance.interval_hours, line_dash="dash", line_color="#D99643")
    st.plotly_chart(plot_style(avail_plot, "Long-run system availability vs planned replacement interval",
                               "Planned interval (operating h)", "Availability (%)"), use_container_width=True)
    st.caption("The age-replacement policy assumes as-new restoration, fixed repair durations and independent failure cycles. "
               "Weibull parameters must be estimated from actual lifetime records for operational use.")

with decision:
    st.subheader("Compare strategies and export reproducible results")
    comparisons = [("Baseline: 100% speed", baseline), ("Selected speed", chosen), ("Optimized within bounds", optimized)]
    exported_comparisons = []
    for label, res in comparisons:
        if res is not None:
            exported_comparisons.append({
                "Strategy": label,
                "Speed (%)": round(100 * res.duty.speed_ratio, 2),
                "PM interval (operating h)": format_interval(res.maintenance.interval_hours),
                "Electric input (kW)": round(res.duty.electric_power_kw, 3),
                "Specific energy (kWh/m³)": round(res.duty.specific_energy_kwh_m3, 5),
                "Throttle head (m)": round(res.duty.throttling_head_m, 2),
                "Expected availability (%)": round(100 * res.maintenance.availability, 3),
                "Expected annual volume (m³)": round(res.expected_annual_volume_m3),
                "Annual electricity (kWh)": round(res.annual_electricity_kwh),
                "Annual emissions (kg CO₂)": round(res.annual_emissions_kgco2),
                "Energy cost ($/year)": round(res.annual_energy_cost),
                "Maintenance cost ($/year)": round(res.annual_maintenance_cost),
                "Downtime cost ($/year)": round(res.annual_downtime_cost),
                "Total cost ($/year)": round(res.annual_total_cost),
            })
    report_df = pd.DataFrame(exported_comparisons)
    st.dataframe(report_df, hide_index=True, use_container_width=True)

    c1, c2 = st.columns(2)
    c1.metric("Optimized estimated annual electricity", f"{optimized.annual_electricity_kwh:,.0f} kWh")
    c2.metric("Optimized annual electricity-associated CO₂", f"{optimized.annual_emissions_kgco2:,.0f} kg")
    if baseline is not None:
        saved_per_m3 = baseline.duty.specific_energy_kwh_m3 - optimized.duty.specific_energy_kwh_m3
        c3, c4 = st.columns(2)
        c3.metric("Energy avoided per 1,000 m³ (equal-flow comparison)", f"{1000 * saved_per_m3:,.1f} kWh")
        c4.metric("CO₂ avoided per 1,000 m³", f"{1000 * saved_per_m3 * grid_factor:,.1f} kg")
    st.caption("Annual kWh and emissions follow each strategy's expected uptime. Avoid comparing those totals "
               "as if both strategies necessarily deliver the same annual volume; use the normalized per-m³ figures.")

    st.markdown("#### Cost landscape across maintenance strategies")
    pm_axis = np.geomspace(low_pm, high_pm, 160)
    objective = [evaluate_strategy(pump, system, flow, lifetime, maintenance, economics,
                                   optimized.duty.speed_ratio, float(p)).annual_total_cost for p in pm_axis]
    cost_fig = go.Figure()
    cost_fig.add_trace(go.Scatter(x=pm_axis, y=objective, mode="lines", name="Preventive replacement",
                                  line=dict(color="#0C8C80", width=3)))
    rtf = evaluate_strategy(pump, system, flow, lifetime, maintenance, economics,
                            optimized.duty.speed_ratio, None)
    cost_fig.add_hline(y=rtf.annual_total_cost, line_dash="dot", line_color="#9F7CC5",
                       annotation_text="Run to failure")
    if optimized.maintenance.interval_hours is not None:
        cost_fig.add_vline(x=optimized.maintenance.interval_hours, line_dash="dash", line_color="#D99643")
    st.plotly_chart(plot_style(cost_fig, "Annual total objective at optimized pump speed",
                               "Preventive interval (operating h)", "Annual total cost ($)"), use_container_width=True)

    st.markdown("#### Download analysis data")
    dl1, dl2, dl3 = st.columns(3)
    dl1.download_button("Download strategy comparison (CSV)", report_df.to_csv(index=False).encode("utf-8"),
                        file_name="reliflow_strategy_comparison.csv", mime="text/csv", use_container_width=True)
    assumptions = {
        "app_version": __version__, "scenario": preset_name,
        "pump": asdict(pump), "system": asdict(system), "lifetime": asdict(lifetime),
        "maintenance": asdict(maintenance), "economics": asdict(economics),
        "required_flow_m3h": flow, "displayed_speed_ratio": selected_speed,
        "baseline_pm_interval_operating_hours": baseline_pm,
        "speed_search_bounds_ratio": [min_speed, max_speed],
        "pm_search_bounds_operating_hours": [low_pm, high_pm],
        "optimized": {"speed_ratio": optimized.duty.speed_ratio,
                      "pm_interval_operating_hours": optimized.maintenance.interval_hours,
                      "annual_total_cost": optimized.annual_total_cost,
                      "availability": optimized.maintenance.availability,
                      "specific_energy_kwh_per_m3": optimized.duty.specific_energy_kwh_m3},
        "source_data_note": "Illustrative data and model estimates; not empirical equipment data",
    }
    dl2.download_button("Download model assumptions (JSON)", json.dumps(assumptions, indent=2).encode("utf-8"),
                        file_name="reliflow_assumptions_and_result.json", mime="application/json",
                        use_container_width=True)
    with dl3:
        with st.popover("Generate and download sensitivity CSV", use_container_width=True):
            st.caption("A reproducible 25-speed × (35-interval + run-to-failure) grid. "
                       "The table is generated from your current assumptions.")
            sens = make_sensitivity(pump, system, flow, lifetime, maintenance,
                                    economics, min_speed, max_speed, low_pm, high_pm)
            st.download_button("Download 900 scenarios (CSV)", sens.to_csv(index=False).encode("utf-8"),
                               file_name="reliflow_sensitivity.csv", mime="text/csv")

with methods:
    st.subheader("Model equations, verification and boundaries")
    st.markdown("**Hydraulics and controlled delivery**")
    st.latex(r"H_p(Q,s)=H_0 s^2-aQ^2;\qquad H_{sys}(Q)=H_{static}+kQ^2")
    st.latex(r"s_{min}=\sqrt{\frac{H_{static}+(a+k)Q_{demand}^2}{H_0}}")
    st.latex(r"P_{electric}=\frac{\rho g (Q/3600)H_p(Q,s)}{1000\,\eta_{pump}\eta_{motor}\eta_{VSD}}\quad[\mathrm{kW}]")
    st.markdown("At any allowed speed, the model fixes flow to the demanded value and dissipates "
                "any surplus pump head across an idealized throttling valve. Open-valve flow is "
                "shown separately as a diagnostic. The assumed efficiency shape is a BEP-centred "
                "quadratic, not a manufacturer's test curve.")
    st.markdown("**Failure and renewal rewards**")
    st.latex(r"R(t)=e^{-(t/\eta)^\beta},\qquad R(a+t\mid X>a)=e^{-((a+t)/\eta)^\beta+(a/\eta)^\beta}")
    st.latex(r"E[U(T)]=\int_0^T R(t)\,dt,\quad E[D(T)]=R(T)d_{PM}+[1-R(T)]d_{CM}")
    st.latex(r"A(T)=\frac{E[U(T)]}{E[U(T)]+E[D(T)]}")
    st.markdown("Maintenance expense per calendar hour is the event-probability-weighted "
                "cost divided by expected cycle calendar duration. The optimizer includes a "
                "run-to-failure option with no scheduled preventive replacement. The annual objective "
                "adds energy cost during expected uptime, preventive/corrective maintenance costs, "
                "and the stated value of downtime. All replacement/repair cycles restore as new.")
    st.markdown("**Technical limitations**")
    st.markdown("""
- Illustrative static head and constant quadratic resistance; **no transient hydraulics, surge, cavitation, NPSH, minimum-flow, viscosity, piping constraints or motor load limits**.
- Speed scaling uses simplified affinity laws and a synthetic BEP efficiency map; verify all conditions against **manufacturer pump curves and motor/VSD ratings**.
- The outage probability model is a **Weibull assumption**, not an inference from the pump curves. No causal speed–failure or maintenance–energy effect is assumed.
- Age replacement implies perfect renewal; it excludes imperfect maintenance, common-cause failures, standby equipment, inspection policy and uncertainty in fitted parameters.
- Constant demand and time-average availability are used. Annual results are expected values, **not measurements, guarantees or a full lifecycle financial assessment**.
- Currency is arbitrary consistent dollars; electricity CO₂ factor is an editable assumption, not a country-specific verified emissions inventory.
- The optimizer is a **finite grid search** over bounded speed and PM intervals, with run to failure. Boundary optima should be checked with wider ranges.
""")
    st.markdown("**Authoritative background references**")
    st.markdown("""
- [Hydraulic Institute — pump curves and affinity rules](https://datatool.pumps.org/pump-fundamentals/pump-curves.html)
- [U.S. Department of Energy — Variable Speed Pumping](https://www.energy.gov/sites/prod/files/2014/05/f16/variable_speed_pumping.pdf)
- [U.S. Department of Energy — Improving Pumping System Performance](https://www.energy.gov/sites/prod/files/2014/05/f16/pump.pdf)
- [NIST/SEMATECH Engineering Statistics Handbook — Weibull](https://www.itl.nist.gov/div898/handbook/apr/section1/apr162.htm)
""")
    st.caption("Use the repository tests for analytical and edge-case checks before relying on model changes.")

st.divider()
st.caption("ReliFlow is an independent computational engineering portfolio project. "
           "Its numerical outputs must not be used to authorize operating changes at any real facility.")
