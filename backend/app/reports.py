from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import HRFlowable, Image, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether

from .dates import to_date, week_bounds
from .domain import annotate, is_closed, is_open, is_overdue, matches_filters, today
from .config import load_config
from .excel.service import excel_service
from .stats import filtered, group_by, kpis, reasons

COLUMNS = [
    ("work_order_id", "IM Work Order #"),
    ("created_date", "MR Received Date"),
    ("description", "Required Material Details"),
    ("department", "Site"),
    ("location", "Location"),
    ("assigned_to", "Assigned To"),
    ("priority", "Priority"),
    ("status", "Status"),
    ("due_date", "Due Date"),
    ("completion_date", "Completion Date"),
    ("closed_date", "Closing Date"),
    ("delay_reason", "Delay Reason"),
    ("remarks", "Remarks"),
    ("work_type", "Work Type"),
    ("issue", "Issue"),
]


def records_for_report(kind: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = load_config()
    recs = filtered(excel_service.get_all(), filters)
    if kind == "open":
        recs = [r for r in recs if is_open(r, cfg)]
    elif kind == "overdue":
        recs = [r for r in recs if is_overdue(r, cfg)]
    elif kind == "closed":
        recs = [r for r in recs if is_closed(r, cfg)]
    elif kind == "delay":
        recs = [r for r in recs if is_open(r, cfg)]
    elif kind in {"daily", "weekly", "monthly", "yearly", "department", "technician"}:
        pass
    recs = [annotate(r, cfg) for r in recs]
    recs.sort(key=lambda r: (r.get("created_date") or ""), reverse=True)
    return recs


def to_csv(records: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in COLUMNS])
    for r in records:
        writer.writerow([r.get(k) or "" for k, _ in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(records: list[dict[str, Any]], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    header_fill = PatternFill("solid", fgColor="0F3D5E")
    header_font = Font(bold=True, color="FFFFFF")
    thin = Border(
        left=Side(style="thin", color="D0D7DE"),
        right=Side(style="thin", color="D0D7DE"),
        top=Side(style="thin", color="D0D7DE"),
        bottom=Side(style="thin", color="D0D7DE"),
    )
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14, color="0F3D5E")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    ws["A2"] = f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    for i, (_, label) in enumerate(COLUMNS, 1):
        cell = ws.cell(4, i, label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin
    for r_i, rec in enumerate(records, 5):
        for c_i, (key, _) in enumerate(COLUMNS, 1):
            cell = ws.cell(r_i, c_i, rec.get(key) or "")
            cell.border = thin
            cell.font = Font(size=9)
    for i, (key, _) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = 18 if key != "description" else 40
    k = kpis(records)
    ws.cell(3, 1, f"Total {k.get('total') or 0} · Open {k.get('open') or 0} · Closed {k.get('closed') or 0} · Overdue {k.get('overdue') or 0}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(records: list[dict[str, Any]], title: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0F3D5E"), spaceAfter=6)
    meta = ParagraphStyle("M", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))
    cell_style = ParagraphStyle("C", parent=styles["Normal"], fontSize=7, leading=9)
    story = [Paragraph(title, title_style), Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  {len(records)} records", meta), Spacer(1, 8)]
    k = kpis(records)
    kpi_data = [
        ["Total", "Open", "Closed", "Overdue", "Completion", "Avg Close (days)"],
        [
            str(k["total"]),
            str(k["open"]),
            str(k["closed"]),
            str(k["overdue"]),
            f"{k['completion_rate']}%",
            str(k["average_closing_days"] if k["average_closing_days"] is not None else "—"),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[40 * mm] * 6)
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    cols = [
        ("work_order_id", "WO #"),
        ("created_date", "Opened"),
        ("department", "Dept"),
        ("assigned_to", "Assigned"),
        ("priority", "Priority"),
        ("status", "Status"),
        ("due_date", "Due"),
        ("delay_reason", "Reason"),
        ("description", "Description"),
    ]
    header = [label for _, label in cols]
    data = [header]
    for rec in records[:400]:
        row = []
        for key, _ in cols:
            val = str(rec.get(key) or "")
            if key in {"created_date", "due_date"}:
                val = val[:10]
            if key == "description":
                val = val[:80]
            row.append(Paragraph(val.replace("&", "&amp;"), cell_style))
        data.append(row)
    widths = [28 * mm, 22 * mm, 28 * mm, 32 * mm, 20 * mm, 24 * mm, 22 * mm, 36 * mm, 60 * mm]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    if len(records) > 400:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Showing first 400 of {len(records)} records. Export Excel/CSV for the full set.", meta))
    doc.build(story)
    return buf.getvalue()


def _esc(value: Any) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wo_sheet_pdf(rec: dict[str, Any], attachments: Optional[list[dict[str, Any]]] = None) -> bytes:
    """One-page A4 sheet for site: material, supplier, PO, due, attachments."""
    attachments = attachments or []
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"IM WO {rec.get('work_order_id') or rec.get('record_id')}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "WOTitle", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0F3D5E"), spaceAfter=4, alignment=0
    )
    meta = ParagraphStyle("WOMeta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"), spaceAfter=2)
    label = ParagraphStyle("WOLabel", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"), leading=11)
    value = ParagraphStyle("WOValue", parent=styles["Normal"], fontSize=10, leading=13, textColor=colors.HexColor("#0F172A"))
    wo = _esc(rec.get("work_order_id") or rec.get("record_id"))
    story: list[Any] = [
        Paragraph(f"IM Work Order {wo}", title_style),
        Paragraph(
            f"Printed {datetime.now().strftime('%Y-%m-%d %H:%M')} · Linkco MR · Excel remains the source of truth",
            meta,
        ),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0F3D5E"), spaceAfter=8),
    ]
    rows = [
        ["Site", rec.get("department") or "—", "Status", rec.get("status") or "—"],
        ["Assigned to", rec.get("assigned_to") or "—", "Priority", rec.get("priority") or "—"],
        ["Purchase type", rec.get("work_type") or "—", "Due date", str(rec.get("due_date") or "—")[:16]],
        ["Supplier", rec.get("supplier") or "—", "PO No", rec.get("po_number") or "—"],
        ["Asset", rec.get("location") or "—", "Delivery", rec.get("issue") or rec.get("delay_reason") or "—"],
        ["MR received", str(rec.get("created_date") or "—")[:16], "ETA", str(rec.get("closed_date") or "—")[:16]],
    ]
    table_data = []
    for a_l, a_v, b_l, b_v in rows:
        table_data.append(
            [
                Paragraph(_esc(a_l), label),
                Paragraph(_esc(a_v), value),
                Paragraph(_esc(b_l), label),
                Paragraph(_esc(b_v), value),
            ]
        )
    grid = Table(table_data, colWidths=[28 * mm, 63 * mm, 28 * mm, 63 * mm])
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(grid)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Required material", label))
    story.append(Paragraph(_esc(rec.get("description") or "—")[:1200], value))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Remarks / notes", label))
    story.append(Paragraph(_esc(rec.get("remarks") or "—")[:1200].replace("\n", "<br/>"), value))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Attachments", label))
    if attachments:
        for item in attachments[:20]:
            note = f" — {_esc(item.get('note'))}" if item.get("note") else ""
            story.append(
                Paragraph(
                    f"• {_esc(item.get('filename'))} ({_esc(item.get('kind') or 'file')}, {_esc(item.get('created_by'))} {_esc(str(item.get('created_at') or '')[:16])}){note}",
                    value,
                )
            )
    else:
        story.append(Paragraph("No files attached in the app.", value))
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Formulas, SN and due-date columns in Excel are not printed. Take this sheet to site; update the workbook in Linkco MR after the visit.",
            meta,
        )
    )
    doc.build([KeepTogether(story)])
    return buf.getvalue()


def _signature_image(data_url: Any):
    raw = str(data_url or "").strip()
    if not raw:
        return None
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        import base64

        blob = base64.b64decode(raw)
        if not blob:
            return None
        reader = ImageReader(io.BytesIO(blob))
        iw, ih = reader.getSize()
        max_w, max_h = 80 * mm, 28 * mm
        aspect = (iw / ih) if ih else 2.8
        width, height = max_w, max_w / max(aspect, 0.1)
        if height > max_h:
            height = max_h
            width = height * aspect
        return Image(reader, width=width, height=height)
    except Exception:
        return None


def po_approval_pdf(rec: dict[str, Any], approval: Optional[dict[str, Any]] = None) -> bytes:
    """PDF the operational manager signs: PO, items, prices, signature."""
    approval = approval or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"PO {rec.get('po_number') or rec.get('work_order_id')}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "POTitle", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0F3D5E"), spaceAfter=4, alignment=0
    )
    meta = ParagraphStyle("POMeta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"), spaceAfter=2)
    label = ParagraphStyle("POLabel", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"), leading=11)
    value = ParagraphStyle("POValue", parent=styles["Normal"], fontSize=10, leading=13, textColor=colors.HexColor("#0F172A"))
    wo = _esc(rec.get("work_order_id") or rec.get("record_id"))
    story: list[Any] = [
        Paragraph(f"Purchase order · IM WO {wo}", title_style),
        Paragraph(
            f"Printed {datetime.now().strftime('%Y-%m-%d %H:%M')} · Linkco MR · state { _esc(approval.get('state') or 'none') }",
            meta,
        ),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0F3D5E"), spaceAfter=8),
    ]
    rows = [
        ["Site", rec.get("site_display") or rec.get("department") or "—", "Status", rec.get("status") or "—"],
        ["Assigned to", rec.get("assigned_to") or "—", "PO technician", approval.get("assignee") or "—"],
        ["Supplier", rec.get("supplier") or "—", "PO No", rec.get("po_number") or "—"],
        ["Purchase type", rec.get("work_type") or "—", "Due date", str(rec.get("due_date") or "—")[:10]],
        ["ETA", str(rec.get("closed_date") or "—")[:16], "RFQ / PO date", str(rec.get("scheduled_date") or "—")[:16]],
        ["Unit price", rec.get("unit_price") or "—", "Price", rec.get("price") or "—"],
        ["Total price", rec.get("total_price") or "—", "Final price", rec.get("final_price") or "—"],
    ]
    table_data = []
    for a_l, a_v, b_l, b_v in rows:
        table_data.append(
            [
                Paragraph(_esc(a_l), label),
                Paragraph(_esc(a_v), value),
                Paragraph(_esc(b_l), label),
                Paragraph(_esc(b_v), value),
            ]
        )
    grid = Table(table_data, colWidths=[28 * mm, 63 * mm, 28 * mm, 63 * mm])
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(grid)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Items", label))
    lines = [ln for ln in (rec.get("lines") or []) if ln.get("supplier") or ln.get("material")]
    if lines:
        data = [["Supplier", "Item", "Qty", "Unit", "Unit price"]]
        for ln in lines[:40]:
            data.append(
                [
                    Paragraph(_esc(ln.get("supplier")), value),
                    Paragraph(_esc(ln.get("material")), value),
                    Paragraph(_esc(ln.get("qty")), value),
                    Paragraph(_esc(ln.get("unit")), value),
                    Paragraph(_esc(ln.get("unit_price")), value),
                ]
            )
        tbl = Table(data, colWidths=[40 * mm, 70 * mm, 18 * mm, 18 * mm, 36 * mm], repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(tbl)
    else:
        story.append(Paragraph(_esc(rec.get("description") or "—")[:1200], value))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Authorized signature", label))
    story.append(
        Paragraph(
            f"State: {_esc(approval.get('state') or 'none')} · signed by {_esc(approval.get('signed_by') or '—')} "
            f"{_esc(str(approval.get('signed_at') or '')[:16])}",
            value,
        )
    )
    if approval.get("comment"):
        story.append(Paragraph(_esc(approval.get("comment"))[:800], value))
    sig = _signature_image(approval.get("signature_png"))
    if sig:
        story.append(Spacer(1, 8))
        block = Table(
            [
                [sig],
                [HRFlowable(width="80mm", thickness=0.6, color=colors.HexColor("#0F172A"), spaceBefore=2, spaceAfter=2)],
                [
                    Paragraph(
                        f"{_esc(approval.get('signed_by') or 'Authorized signatory')}<br/>"
                        f"{_esc(str(approval.get('signed_at') or '')[:16])}",
                        meta,
                    )
                ],
            ],
            colWidths=[90 * mm],
        )
        block.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(block)
    else:
        story.append(Paragraph("No signature on file yet.", meta))
    doc.build(story)
    return buf.getvalue()


def digest_pdf(payload: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Morning digest",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DigTitle", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0F3D5E"), spaceAfter=4, alignment=0
    )
    meta = ParagraphStyle("DigMeta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"), spaceAfter=2)
    h2 = ParagraphStyle("DigH2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0F3D5E"), spaceBefore=8, spaceAfter=4)
    h3 = ParagraphStyle("DigH3", parent=styles["Heading3"], fontSize=10, textColor=colors.HexColor("#334155"), spaceBefore=4, spaceAfter=2)
    cell = ParagraphStyle("DigC", parent=styles["Normal"], fontSize=7, leading=9)
    counts = payload.get("counts") or {}
    story: list[Any] = [
        Paragraph("Linkco MR · morning digest", title_style),
        Paragraph(
            f"Printed {datetime.now().strftime('%Y-%m-%d %H:%M')} · as of { _esc(payload.get('as_of')) } · "
            f"overdue {counts.get('overdue', 0)} · NTP {counts.get('ntp', 0)} · due soon {counts.get('due_soon', 0)} · live Excel",
            meta,
        ),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0F3D5E"), spaceAfter=6),
    ]
    for section in payload.get("sections") or []:
        story.append(Paragraph(f"{_esc(section.get('title'))} ({section.get('count') or 0})", h2))
        sites = section.get("sites") or []
        if not sites:
            story.append(Paragraph("None.", cell))
            continue
        for site in sites:
            story.append(Paragraph(f"{_esc(site.get('name'))} · {site.get('count') or 0}", h3))
            for person in site.get("assignees") or []:
                rows = [["WO #", "Material", "Due / age", "Status", "Assigned"]]
                for rec in person.get("items") or []:
                    due = str(rec.get("due_date") or "")[:10]
                    age = rec.get("days_overdue")
                    if age is None:
                        age = rec.get("aging_days")
                    rows.append(
                        [
                            Paragraph(_esc(rec.get("work_order_id")), cell),
                            Paragraph(_esc(str(rec.get("description") or "")[:80]), cell),
                            Paragraph(_esc(due or age or "—"), cell),
                            Paragraph(_esc(rec.get("status")), cell),
                            Paragraph(_esc(rec.get("assigned_to") or person.get("name")), cell),
                        ]
                    )
                table = Table(rows, colWidths=[28 * mm, 70 * mm, 28 * mm, 28 * mm, 32 * mm], repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 7),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                            ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                            ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(Paragraph(_esc(person.get("name")) + f" · {person.get('count') or 0}", cell))
                story.append(table)
                story.append(Spacer(1, 4))
    doc.build(story)
    return buf.getvalue()



LIST_CAP = 8
PDF_LIST_CAP = 5


def _as_of(filters: dict[str, Any]) -> date:
    return to_date(filters.get("as_of") or filters.get("date") or filters.get("date_from")) or today()


def _window(kind: str, as_of: date) -> tuple[date, date, str]:
    if kind == "daily":
        return as_of, as_of, as_of.strftime("%d %b %Y")
    iso = as_of.isocalendar()
    start_dt, end_dt = week_bounds(int(iso[0]), int(iso[1]))
    start, end = start_dt.date(), end_dt.date()
    return start, end, f"Week {int(iso[1])} · {start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def _in_window(value: Any, start: date, end: date) -> bool:
    day = to_date(value)
    return bool(day and start <= day <= end)


def _closed_on(rec: dict[str, Any], start: date, end: date, cfg) -> bool:
    if not is_closed(rec, cfg):
        return False
    return _in_window(rec.get("closed_date"), start, end) or _in_window(rec.get("completion_date"), start, end)


def _field_ok(rec: dict[str, Any], filters: dict[str, Any]) -> bool:
    for field in ("department", "assigned_to", "status"):
        raw = filters.get(field)
        if not raw:
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        values = [str(v) for v in values if str(v).strip()]
        if not values:
            continue
        current = str(rec.get(field) or "")
        lowered = {v.lower() for v in values}
        if current not in values and current.lower() not in lowered:
            return False
    return True


def _slim(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": rec.get("record_id"),
        "work_order_id": rec.get("work_order_id") or rec.get("record_id"),
        "department": rec.get("department") or "",
        "assigned_to": rec.get("assigned_to") or "",
        "status": rec.get("status") or "",
        "priority": rec.get("priority") or "",
        "description": rec.get("description") or "",
        "supplier": rec.get("supplier") or "",
        "due_date": str(rec.get("due_date") or "")[:10],
        "created_date": str(rec.get("created_date") or "")[:10],
    }


def _count_by(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts = Counter(str(r.get(field) or "Unassigned") for r in rows)
    return [{"name": name, "value": n} for name, n in counts.most_common(8)]


def period_payload(kind: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Daily = that calendar day only. Weekly = ISO week of the chosen date only."""
    cfg = load_config()
    kind = "weekly" if kind == "weekly" else "daily"
    as_of = _as_of(filters)
    start, end, label = _window(kind, as_of)
    all_recs = [annotate(r, cfg) for r in excel_service.get_all() if _field_ok(r, filters)]
    created = [r for r in all_recs if _in_window(r.get("created_date"), start, end)]
    closed = [r for r in all_recs if _closed_on(r, start, end, cfg)]
    due = [r for r in all_recs if is_open(r, cfg) and _in_window(r.get("due_date"), start, end)]
    overdue = [r for r in all_recs if is_overdue(r, cfg, on=end)]
    created.sort(key=lambda r: str(r.get("created_date") or ""), reverse=True)
    closed.sort(key=lambda r: str(r.get("closed_date") or r.get("completion_date") or ""), reverse=True)
    overdue.sort(key=lambda r: str(r.get("due_date") or ""))
    due.sort(key=lambda r: str(r.get("due_date") or ""))
    days: list[dict[str, Any]] = []
    if kind == "weekly":
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, name in enumerate(names):
            day = start + timedelta(days=i)
            days.append(
                {
                    "name": name,
                    "date": day.isoformat(),
                    "created": sum(1 for r in created if to_date(r.get("created_date")) == day),
                    "closed": sum(1 for r in closed if _closed_on(r, day, day, cfg)),
                    "overdue": sum(1 for r in all_recs if is_overdue(r, cfg, on=day)),
                }
            )
    return {
        "kind": kind,
        "as_of": as_of.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": label,
        "title": "Daily report" if kind == "daily" else "Weekly report",
        "kpis": {
            "created": len(created),
            "closed": len(closed),
            "overdue": len(overdue),
            "due": len(due),
        },
        "by_site": _count_by(created + closed, "department"),
        "by_status": _count_by(created + overdue, "status"),
        "by_assignee": _count_by(created + overdue, "assigned_to"),
        "days": days,
        "lists": {
            "created": [_slim(r) for r in created[:LIST_CAP]],
            "closed": [_slim(r) for r in closed[:LIST_CAP]],
            "overdue": [_slim(r) for r in overdue[:LIST_CAP]],
            "due": [_slim(r) for r in due[:LIST_CAP]],
        },
        "totals": {
            "created": len(created),
            "closed": len(closed),
            "overdue": len(overdue),
            "due": len(due),
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _period_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("PRTitle", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#0F3D5E"), alignment=0, spaceAfter=2),
        "meta": ParagraphStyle("PRMeta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748B"), spaceAfter=6),
        "h": ParagraphStyle("PRH", parent=styles["Heading2"], fontSize=9.5, leading=12, textColor=colors.HexColor("#0F3D5E"), spaceBefore=6, spaceAfter=2),
        "cell": ParagraphStyle("PRC", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#0F172A")),
        "muted": ParagraphStyle("PRM", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#64748B"), spaceAfter=2),
    }


def _kpi_table(payload: dict[str, Any]) -> Table:
    k = payload.get("kpis") or {}
    data = [
        ["New MRs", "Closed", "Overdue", "Due this period"],
        [str(k.get("created") or 0), str(k.get("closed") or 0), str(k.get("overdue") or 0), str(k.get("due") or 0)],
    ]
    table = Table(data, colWidths=[45 * mm, 45 * mm, 45 * mm, 47 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F0F9FF")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, 1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 1), (-1, 1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#0F3D5E")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
            ]
        )
    )
    return table


def _mini_table(rows: list[dict[str, Any]], headers: list[str], keys: list[str], widths: list[float], styles: dict) -> Table:
    data = [[Paragraph(h, styles["cell"]) for h in headers]]
    if not rows:
        data.append([Paragraph("None.", styles["muted"])] + [""] * (len(headers) - 1))
    for rec in rows:
        data.append([Paragraph(_esc(str(rec.get(k) or "—")[:70]), styles["cell"]) for k in keys])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def period_pdf(payload: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=payload.get("title") or "Report",
    )
    s = _period_styles()
    lists = {key: (rows or [])[:PDF_LIST_CAP] for key, rows in (payload.get("lists") or {}).items()}
    totals = payload.get("totals") or {}
    story: list[Any] = [
        Paragraph(f"Linkco MR · {payload.get('title')}", s["title"]),
        Paragraph(f"{payload.get('label')} · generated {payload.get('generated_at')} · live database", s["meta"]),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#0F3D5E"), spaceAfter=8),
        _kpi_table(payload),
    ]
    days = payload.get("days") or []
    if days:
        story.append(Paragraph("This week by day", s["h"]))
        day_data = [["", *[d["name"] for d in days]]]
        for key, label in (("created", "New"), ("closed", "Closed"), ("overdue", "Overdue")):
            day_data.append([label, *[str(d.get(key) or 0) for d in days]])
        day_table = Table(day_data, colWidths=[28 * mm] + [22 * mm] * 7)
        day_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F3D5E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(day_table)

    def _section(title: str, key: str, headers: list[str], keys: list[str], widths: list[float]) -> None:
        n = totals.get(key) or 0
        extra = f" · showing {min(n, PDF_LIST_CAP)} of {n}" if n > PDF_LIST_CAP else ""
        story.append(Paragraph(title, s["h"]))
        story.append(Paragraph(f"{n}{extra}", s["muted"]))
        story.append(_mini_table(lists.get(key) or [], headers, keys, widths, s))

    _section("New material requests", "created", ["WO #", "Site", "Material", "Assigned", "Status"], ["work_order_id", "department", "description", "assigned_to", "status"], [28 * mm, 24 * mm, 70 * mm, 32 * mm, 28 * mm])
    _section("Closed / completed", "closed", ["WO #", "Site", "Material", "Assigned", "Status"], ["work_order_id", "department", "description", "assigned_to", "status"], [28 * mm, 24 * mm, 70 * mm, 32 * mm, 28 * mm])
    _section("Still overdue", "overdue", ["WO #", "Site", "Due", "Assigned", "Status"], ["work_order_id", "department", "due_date", "assigned_to", "status"], [28 * mm, 28 * mm, 28 * mm, 40 * mm, 58 * mm])

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(12 * mm, 8 * mm, "Linkco MR · Al Rawabet Commercial Services")
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, "Page 1")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def period_xlsx(payload: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Daily" if payload.get("kind") == "daily" else "Weekly"
    navy = PatternFill("solid", fgColor="0F3D5E")
    white = Font(bold=True, color="FFFFFF", size=10)
    thin = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    ws["A1"] = f"Linkco MR · {payload.get('title')}"
    ws["A1"].font = Font(bold=True, size=16, color="0F3D5E")
    ws.merge_cells("A1:E1")
    ws["A2"] = payload.get("label")
    ws["A2"].font = Font(size=11, color="64748B")
    k = payload.get("kpis") or {}
    headers = ["New MRs", "Closed", "Overdue", "Due this period"]
    values = [k.get("created") or 0, k.get("closed") or 0, k.get("overdue") or 0, k.get("due") or 0]
    for i, (h, v) in enumerate(zip(headers, values), 1):
        cell_h = ws.cell(4, i, h)
        cell_h.fill = navy
        cell_h.font = white
        cell_h.alignment = Alignment(horizontal="center")
        cell_v = ws.cell(5, i, v)
        cell_v.font = Font(bold=True, size=16, color="0F3D5E")
        cell_v.alignment = Alignment(horizontal="center")
        cell_h.border = thin
        cell_v.border = thin
    row = 7
    days = payload.get("days") or []
    if days:
        ws.cell(row, 1, "This week by day").font = Font(bold=True, color="0F3D5E")
        row += 1
        for i, d in enumerate(days, 2):
            c = ws.cell(row, i, d["name"])
            c.fill = navy
            c.font = white
            c.alignment = Alignment(horizontal="center")
        row += 1
        for key, label in (("created", "New"), ("closed", "Closed"), ("overdue", "Overdue")):
            ws.cell(row, 1, label)
            for i, d in enumerate(days, 2):
                ws.cell(row, i, d.get(key) or 0).alignment = Alignment(horizontal="center")
            row += 1
        row += 1
    lists = payload.get("lists") or {}
    totals = payload.get("totals") or {}
    for key, title, cols in (
        ("created", "New material requests", ["work_order_id", "department", "description", "assigned_to", "status"]),
        ("closed", "Closed / completed", ["work_order_id", "department", "description", "assigned_to", "status"]),
        ("overdue", "Still overdue", ["work_order_id", "department", "due_date", "assigned_to", "status"]),
    ):
        ws.cell(row, 1, f"{title} ({totals.get(key) or 0})").font = Font(bold=True, color="0F3D5E")
        row += 1
        labels = ["WO #", "Site", "Material / Due", "Assigned", "Status"]
        for i, lab in enumerate(labels, 1):
            c = ws.cell(row, i, lab)
            c.fill = navy
            c.font = white
            c.border = thin
        row += 1
        items = lists.get(key) or []
        if not items:
            ws.cell(row, 1, "None.")
            row += 2
            continue
        for rec in items:
            for i, col in enumerate(cols, 1):
                cell = ws.cell(row, i, rec.get(col) or "")
                cell.border = thin
                cell.font = Font(size=10)
            row += 1
        row += 1
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 42
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 16
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def period_csv(payload: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Linkco MR", payload.get("title"), payload.get("label")])
    k = payload.get("kpis") or {}
    writer.writerow(["New MRs", "Closed", "Overdue", "Due this period"])
    writer.writerow([k.get("created") or 0, k.get("closed") or 0, k.get("overdue") or 0, k.get("due") or 0])
    writer.writerow([])
    for key, title in (("created", "New"), ("closed", "Closed"), ("overdue", "Overdue")):
        writer.writerow([title])
        writer.writerow(["WO #", "Site", "Material", "Assigned", "Status", "Due"])
        for rec in (payload.get("lists") or {}).get(key) or []:
            writer.writerow([rec.get("work_order_id"), rec.get("department"), rec.get("description"), rec.get("assigned_to"), rec.get("status"), rec.get("due_date")])
        writer.writerow([])
    return buf.getvalue().encode("utf-8-sig")



def render(kind: str, fmt: str, filters: dict[str, Any]) -> tuple[bytes, str, str]:
    kind = (kind or "").lower()
    fmt = (fmt or "pdf").lower()
    stamp = datetime.now().strftime("%Y%m%d")
    if kind in {"daily", "weekly"}:
        payload = period_payload(kind, filters)
        slug = f"{kind}_{payload['start']}"
        if fmt == "json":
            import json

            return json.dumps(payload).encode("utf-8"), f"{slug}.json", "application/json"
        if fmt == "csv":
            return period_csv(payload), f"{slug}.csv", "text/csv"
        if fmt == "xlsx":
            return period_xlsx(payload), f"{slug}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if fmt == "pdf":
            return period_pdf(payload), f"{slug}.pdf", "application/pdf"
        raise ValueError(f"Unsupported format {fmt}")
