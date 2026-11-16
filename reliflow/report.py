"""Two-page-or-less educational PDF engineering summary for ReliFlow."""
from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from .optimization import StrategyMetrics
from .suction import NPSHScreen, SuctionSpec


def make_report_pdf(
    scenario: str, version: str, flow_m3h: float,
    optimized: StrategyMetrics, baseline: StrategyMetrics | None,
    suction: SuctionSpec | None = None, npsh: NPSHScreen | None = None,
) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="ReliFlow engineering assessment", author="ReliFlow educational engineering portfolio",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitleCustom", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#123044"), spaceAfter=8))
    styles.add(ParagraphStyle(name="ReportSmallCustom", parent=styles["BodyText"], fontSize=9, leading=13))
    styles.add(ParagraphStyle(name="ReportHeadingCustom", parent=styles["Heading2"], fontSize=11, leading=15, textColor=colors.HexColor("#087F76"), spaceBefore=12))
    story = [
        Paragraph("ReliFlow | Engineering Assessment", styles["ReportTitleCustom"]),
        Paragraph(f"Scenario: {escape(scenario)} &nbsp;&nbsp; Version: {escape(version)}", styles["ReportSmallCustom"]),
        Spacer(1, 8),
        Paragraph("Purpose and analysis", styles["ReportHeadingCustom"]),
        Paragraph("Educational fixed-flow pump-energy and Weibull maintenance evaluation. "
                  "Reported values are mathematical estimates using synthetic example parameters, "
                  "not measured equipment performance or operational advice.", styles["ReportSmallCustom"]),
        Paragraph("Recommended single-pump operating strategy", styles["ReportHeadingCustom"]),
    ]
    def policy(result: StrategyMetrics) -> str:
        return "Run to failure" if result.maintenance.interval_hours is None else f"{result.maintenance.interval_hours:,.0f} operating h"
    rows = [
        ("Parameter", "Optimized", "Baseline"),
        ("Required flow (m3/h)", f"{flow_m3h:,.2f}", f"{flow_m3h:,.2f}" if baseline else "N/A"),
        ("Pump speed (% ref)", f"{100 * optimized.duty.speed_ratio:.2f}", f"{100 * baseline.duty.speed_ratio:.2f}" if baseline else "N/A"),
        ("Planned renewal interval", policy(optimized), policy(baseline) if baseline else "N/A"),
        ("Electric input (kW)", f"{optimized.duty.electric_power_kw:,.2f}", f"{baseline.duty.electric_power_kw:,.2f}" if baseline else "N/A"),
        ("Energy intensity (kWh/m3)", f"{optimized.duty.specific_energy_kwh_m3:,.4f}", f"{baseline.duty.specific_energy_kwh_m3:,.4f}" if baseline else "N/A"),
        ("Expected availability (%)", f"{optimized.maintenance.availability * 100:.2f}", f"{baseline.maintenance.availability * 100:.2f}" if baseline else "N/A"),
        ("Annual total cost (model $)", f"{optimized.annual_total_cost:,.0f}", f"{baseline.annual_total_cost:,.0f}" if baseline else "N/A"),
    ]
    tab = Table(rows, colWidths=[70 * mm, 45 * mm, 45 * mm], repeatRows=1, hAlign="LEFT")
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123044")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F6F8")]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#A5B8C1")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [Spacer(1, 5), tab]
    if suction is not None and npsh is not None:
        verdict = "PASS (illustrative screen only)" if npsh.passes_requested_margin else "BELOW REQUESTED MARGIN (investigate)"
        story += [Paragraph("Suction-side NPSH screening", styles["ReportHeadingCustom"]),
                  Paragraph(f"NPSH available = {npsh.available_m:.2f} m; NPSH required (approx.) = "
                            f"{npsh.required_m:.2f} m; NPSHa/NPSHr = {npsh.margin_ratio:.2f}; "
                            f"user margin target = {suction.required_margin_ratio:.2f}. "
                            f"Screen verdict: {verdict}.", styles["ReportSmallCustom"])]
    story += [
        Paragraph("Model scope and limitations", styles["ReportHeadingCustom"]),
        Paragraph("Steady-state single-pump energy and renewal-reward availability are modeled independently. "
                  "No manufacturer pump curve, measured failure distribution, actual suction piping survey, "
                  "or cavitation acceptance criteria are supplied. NPSHr scales approximately with speed squared "
                  "for illustrative screening; real acceptance requires manufacturer data. "
                  "Parallel active-pump comparisons and Weibull parameter scenarios, when shown in the dashboard, "
                  "are diagnostics, not part of the reported optimized single-pump objective.",
                  styles["ReportSmallCustom"]),
        Spacer(1, 14),
        Paragraph("This report must not be used to authorize process changes, equipment design, "
                  "safety decisions or financial commitments.", styles["ReportSmallCustom"]),
    ]
    doc.build(story)
    return output.getvalue()
