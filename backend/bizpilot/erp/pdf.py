from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    from bizpilot.erp.models import Invoice


def generate_invoice_pdf(invoice: Invoice) -> bytes:
    """Generate a high-quality PDF document for the given invoice.

    Returns:
        bytes: Raw PDF file bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "InvoiceSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    bold_label_style = ParagraphStyle(
        "BoldLabel",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold",
    )
    cell_style = ParagraphStyle(
        "CellContent",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    cell_right = ParagraphStyle(
        "CellRight",
        parent=cell_style,
        alignment=2,  # Right aligned
    )
    header_cell = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#ffffff"),
        fontName="Helvetica-Bold",
    )
    header_right = ParagraphStyle(
        "HeaderRight",
        parent=header_cell,
        alignment=2,
    )

    story = []

    # Header section: Business on left, INVOICE info on right
    business_name = invoice.business_name or (invoice.organization.name if invoice.organization else "BizPilot Business")
    biz_info = [
        Paragraph(business_name, title_style),
        Paragraph(invoice.business_email or "", subtitle_style),
        Paragraph(invoice.business_address or "", subtitle_style),
        Paragraph(invoice.business_phone or "", subtitle_style),
    ]

    inv_meta = [
        Paragraph(f"<b>INVOICE</b> #{invoice.invoice_number}", ParagraphStyle("InvHead", parent=title_style, fontSize=18, alignment=2)),
        Paragraph(f"<b>Status:</b> {invoice.status.upper()}", ParagraphStyle("InvStatus", parent=subtitle_style, alignment=2)),
        Paragraph(f"<b>Issue Date:</b> {invoice.issue_date}", ParagraphStyle("InvDate", parent=subtitle_style, alignment=2)),
        Paragraph(f"<b>Due Date:</b> {invoice.due_date}", ParagraphStyle("InvDue", parent=subtitle_style, alignment=2)),
    ]

    header_table = Table(
        [[biz_info, inv_meta]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=14))

    # Bill To block
    bill_to_info = [
        Paragraph("<b>BILLED TO:</b>", bold_label_style),
        Paragraph(invoice.client_name or (invoice.client.name if invoice.client else "Client"), bold_label_style),
        Paragraph(invoice.client_email or "", subtitle_style),
        Paragraph(invoice.client_address or "", subtitle_style),
    ]
    story.append(Table([[bill_to_info]], colWidths=[7 * inch]))
    story.append(Spacer(1, 14))

    # Items table
    items_data = [
        [
            Paragraph("Item & Description", header_cell),
            Paragraph("Qty", header_right),
            Paragraph("Rate", header_right),
            Paragraph("Amount", header_right),
        ]
    ]

    for item in invoice.items.all():
        items_data.append([
            Paragraph(item.description or (item.product.name if item.product else "Item"), cell_style),
            Paragraph(f"{item.quantity}", cell_right),
            Paragraph(f"{item.rate} {invoice.currency}", cell_right),
            Paragraph(f"{item.amount} {invoice.currency}", cell_right),
        ])

    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
    ]

    items_table = Table(
        items_data,
        colWidths=[3.8 * inch, 0.9 * inch, 1.1 * inch, 1.2 * inch],
    )
    items_table.setStyle(TableStyle(table_style))
    story.append(items_table)
    story.append(Spacer(1, 14))

    # Summary Totals
    totals_data = [
        [Paragraph("Subtotal:", cell_right), Paragraph(f"{invoice.subtotal} {invoice.currency}", cell_right)],
    ]
    if invoice.tax_amount and invoice.tax_amount > 0:
        totals_data.append([
            Paragraph(f"Tax ({invoice.tax_rate}%):", cell_right),
            Paragraph(f"{invoice.tax_amount} {invoice.currency}", cell_right),
        ])
    if invoice.discount_amount and invoice.discount_amount > 0:
        totals_data.append([
            Paragraph("Discount:", cell_right),
            Paragraph(f"-{invoice.discount_amount} {invoice.currency}", cell_right),
        ])
    totals_data.append([
        Paragraph("<b>Total:</b>", cell_right),
        Paragraph(f"<b>{invoice.total} {invoice.currency}</b>", cell_right),
    ])
    totals_data.append([
        Paragraph("Paid Amount:", cell_right),
        Paragraph(f"{invoice.paid_amount} {invoice.currency}", cell_right),
    ])
    totals_data.append([
        Paragraph("<b>Balance Due:</b>", ParagraphStyle("BalDue", parent=bold_label_style, alignment=2, textColor=colors.HexColor("#b91c1c"))),
        Paragraph(f"<b>{invoice.balance_due} {invoice.currency}</b>", ParagraphStyle("BalDueVal", parent=bold_label_style, alignment=2, textColor=colors.HexColor("#b91c1c"))),
    ])

    totals_table = Table(
        totals_data,
        colWidths=[5.5 * inch, 1.5 * inch],
    )
    totals_table.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEABOVE", (0, -2), (-1, -2), 1, colors.HexColor("#cbd5e1")),
        ])
    )
    story.append(totals_table)

    # Notes & Terms
    if invoice.notes or invoice.terms:
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=10))
        if invoice.notes:
            story.append(Paragraph(f"<b>Notes:</b> {invoice.notes}", subtitle_style))
        if invoice.terms:
            story.append(Paragraph(f"<b>Terms:</b> {invoice.terms}", subtitle_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
