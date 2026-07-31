"""Build the techno-economic model as a live-formula workbook.

Every number a reader might question is an input cell with a stated basis, and
every derived number is an Excel formula referencing those cells — so the model
can be re-run with different assumptions without trusting anything computed here.

No competitor price is asserted anywhere. Published pricing for SmartFresh,
HarvestHold Fresh, Vidre+ and Hazel 100 was not retrievable, and inventing a
benchmark would be a fabrication. The comparison is left as an input for the
reader to supply.
"""
from __future__ import annotations

import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cost_model.xlsx")

HDR = Font(bold=True, color="FFFFFF")
HDRFILL = PatternFill("solid", fgColor="2F4858")
INPUT = PatternFill("solid", fgColor="FFF3CD")   # yellow = you may edit
DERIVED = PatternFill("solid", fgColor="E7F1FF")  # blue = formula
SECTION = Font(bold=True)

# (label, value, unit, basis) — value None marks a section header.
INPUTS = [
    ("MATERIAL PRICES", None, "", ""),
    ("Base paper price", 1.20, "USD/kg", "ASSUMPTION — commodity coated/uncoated paper stock; replace with a supplier quote"),
    ("Binder price", 4.00, "USD/kg", "ASSUMPTION — spans PEG / shellac / latex; replace per binder chosen"),
    ("1-MCP/alpha-CD complex price", 120.00, "USD/kg", "ASSUMPTION — speciality complex, NOT verified. Dominant uncertainty in this model"),
    ("Protective overwrap price", 0.020, "USD/insert", "ASSUMPTION — barrier film pouch"),
    ("", None, "", ""),
    ("PRODUCT SPECIFICATION", None, "", ""),
    ("Base paper grammage", 120.0, "g/m2", "Proposed starting range 80-200 (Section 9.2)"),
    ("Total dry coat weight", 10.0, "g/m2", "Proposed starting range 4-20 (Section 9.2); no retrieved source reports this"),
    ("Complex fraction of dry coating", 0.25, "w/w", "Proposed starting range 0.10-0.40"),
    ("1-MCP content of complex", 0.03, "w/w", "ASSUMPTION — typical order for alpha-CD inclusion complexes; MUST be verified by assay"),
    ("Insert area", 0.02, "m2", "ASSUMPTION — approx. 141 x 141 mm insert"),
    ("", None, "", ""),
    ("CONVERSION AND OVERHEAD", None, "", ""),
    ("Coating + drying cost", 0.15, "USD/m2", "ASSUMPTION — roll-to-roll converting; scale-sensitive"),
    ("Converting/die-cutting cost", 0.08, "USD/m2", "ASSUMPTION"),
    ("Quality control per insert", 0.005, "USD/insert", "ASSUMPTION — sampling-based release QC"),
    ("Material utilisation yield", 0.85, "fraction", "ASSUMPTION — coating and die-cut waste"),
    ("Overhead and margin multiplier", 1.35, "x", "ASSUMPTION — applied to fully loaded cost"),
    ("", None, "", ""),
    ("APPLICATION CONTEXT", None, "", ""),
    ("Produce mass per package", 5.0, "kg", "Set to the target commodity's carton (Section 13)"),
    ("Inserts per package", 1.0, "count", "Design choice; revisit if dose scales with volume"),
    ("", None, "", ""),
    ("BENCHMARK (user-supplied)", None, "", ""),
    ("Incumbent consumable cost per package", 0.0, "USD/package", "LEAVE 0 UNLESS YOU HAVE A REAL QUOTE. No published price was retrievable; a fabricated benchmark would invalidate the comparison"),
]


def build() -> str:
    wb = Workbook()

    # ---- Inputs sheet ----
    ws = wb.active
    ws.title = "Inputs"
    ws.append(["Parameter", "Value", "Unit", "Basis / source"])
    for c in ws[1]:
        c.font = HDR
        c.fill = HDRFILL
    row_of: dict[str, int] = {}
    for label, value, unit, basis in INPUTS:
        ws.append([label, value, unit, basis])
        r = ws.max_row
        if value is None:
            ws.cell(row=r, column=1).font = SECTION
            continue
        row_of[label] = r
        ws.cell(row=r, column=2).fill = INPUT
    for col, width in zip("ABCD", (42, 14, 12, 78)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=4).alignment = Alignment(wrap_text=True, vertical="top")

    def ref(label: str) -> str:
        return f"Inputs!B{row_of[label]}"

    # ---- Cost build-up ----
    cs = wb.create_sheet("Cost build-up")
    cs.append(["Line", "Formula basis", "Value", "Unit"])
    for c in cs[1]:
        c.font = HDR
        c.fill = HDRFILL

    lines = [
        ("Paper cost", f"={ref('Base paper grammage')}/1000*{ref('Base paper price')}", "USD/m2"),
        ("Complex mass in coating", f"={ref('Total dry coat weight')}*{ref('Complex fraction of dry coating')}", "g/m2"),
        ("Binder mass in coating", f"={ref('Total dry coat weight')}*(1-{ref('Complex fraction of dry coating')})", "g/m2"),
        ("Complex cost", f"=C3/1000*{ref('1-MCP/alpha-CD complex price')}", "USD/m2"),
        ("Binder cost", f"=C4/1000*{ref('Binder price')}", "USD/m2"),
        ("Coating + drying", f"={ref('Coating + drying cost')}", "USD/m2"),
        ("Converting", f"={ref('Converting/die-cutting cost')}", "USD/m2"),
        ("Subtotal per m2 (before yield)", "=C2+C5+C6+C7+C8", "USD/m2"),
        ("Adjusted for yield", f"=C9/{ref('Material utilisation yield')}", "USD/m2"),
        ("", "", ""),
        ("Cost per insert (materials+conversion)", f"=C10*{ref('Insert area')}", "USD/insert"),
        ("Overwrap", f"={ref('Protective overwrap price')}", "USD/insert"),
        ("Quality control", f"={ref('Quality control per insert')}", "USD/insert"),
        ("Fully loaded cost per insert", "=C12+C13+C14", "USD/insert"),
        ("With overhead and margin", f"=C15*{ref('Overhead and margin multiplier')}", "USD/insert"),
        ("", "", ""),
        ("Cost per package", f"=C16*{ref('Inserts per package')}", "USD/package"),
        ("Cost per kg produce protected", f"=C18/{ref('Produce mass per package')}", "USD/kg"),
        ("", "", ""),
        ("1-MCP delivered per insert", f"=C3*{ref('Insert area')}*{ref('1-MCP content of complex')}*1000", "mg"),
        ("Delta vs benchmark (negative = cheaper)", f"=C18-{ref('Incumbent consumable cost per package')}", "USD/package"),
    ]
    for label, formula, unit in lines:
        cs.append([label, formula if formula else "", formula if formula else None, unit])
        r = cs.max_row
        if formula:
            cs.cell(row=r, column=3).value = formula
            cs.cell(row=r, column=3).fill = DERIVED
            cs.cell(row=r, column=3).number_format = "0.0000"
        cs.cell(row=r, column=2).value = formula.replace("Inputs!", "") if formula else ""
    for lbl in ("Fully loaded cost per insert", "With overhead and margin",
                "Cost per package", "Cost per kg produce protected"):
        for row in cs.iter_rows(min_col=1, max_col=1):
            if row[0].value == lbl:
                row[0].font = SECTION
    for col, width in zip("ABCD", (40, 46, 16, 14)):
        cs.column_dimensions[col].width = width
    cs.freeze_panes = "A2"

    # ---- Sensitivity ----
    ss = wb.create_sheet("Sensitivity")
    ss.append(["Driver", "Why it dominates", "Low", "Base", "High"])
    for c in ss[1]:
        c.font = HDR
        c.fill = HDRFILL
    for row in [
        ["Complex price (USD/kg)", "Unverified and the largest single input; a 5x error moves the answer more than everything else combined", 40, 120, 400],
        ["Coat weight (g/m2)", "Scales complex usage linearly and is the main release-control lever", 4, 10, 20],
        ["Complex fraction (w/w)", "Scales complex usage linearly", 0.10, 0.25, 0.40],
        ["Insert area (m2)", "Scales total material per package", 0.01, 0.02, 0.04],
        ["Coating + drying (USD/m2)", "Falls sharply with volume; dominant at low volume", 0.05, 0.15, 0.50],
        ["Yield (fraction)", "Poor yield on a speciality active is expensive", 0.70, 0.85, 0.95],
    ]:
        ss.append(row)
    for col, width in zip("ABCDE", (30, 74, 10, 10, 10)):
        ss.column_dimensions[col].width = width
    for r in range(2, ss.max_row + 1):
        ss.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ss.freeze_panes = "A2"

    # ---- Notes ----
    ns = wb.create_sheet("Notes")
    for line in [
        "TECHNO-ECONOMIC MODEL — READ FIRST",
        "",
        "Yellow cells on Inputs are assumptions you may edit. Blue cells are formulas.",
        "",
        "1. Every material price here is an ASSUMPTION, not a quotation. The 1-MCP/alpha-CD",
        "   complex price is the largest input and the least certain; it should be replaced",
        "   with a supplier quote before any decision rests on this model.",
        "2. The 1-MCP content of the complex (3% w/w) is an assumed order of magnitude and",
        "   must be confirmed by assay. It does not affect cost, but it determines whether the",
        "   delivered payload is anywhere near an effective dose.",
        "3. No incumbent price is asserted. Published pricing for SmartFresh, HarvestHold",
        "   Fresh, Vidre+ and Hazel 100 was not retrievable during this review, and inventing",
        "   a benchmark would invalidate the comparison. Supply a real quote in the benchmark",
        "   cell to activate the delta calculation.",
        "4. Registration and compliance costs are NOT in this model. For a pesticide-active",
        "   product they are potentially larger than manufacturing cost and are treated as a",
        "   programme cost in Section 14, not a per-unit cost.",
        "5. Coating and drying cost is strongly volume-sensitive. At pilot volumes the true",
        "   figure may exceed the 'High' sensitivity case by an order of magnitude.",
    ]:
        ns.append([line])
    ns.column_dimensions["A"].width = 100

    wb.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
