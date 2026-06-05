import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# Logo path
LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "aston_logo.png")


def build_invoice_pdf(order) -> io.BytesIO:
    """
    Build a PDF invoice for the given order.
    
    Args:
        order: Order_Customer object with loaded relationships
              (mou, customer, status, order_details.mou_product.product)
    
    Returns:
        BytesIO buffer containing the PDF data
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # -- Colors --
    primary_color = colors.HexColor("#1a56db")
    header_bg = colors.HexColor("#1a56db")
    header_text = colors.white
    light_gray = colors.HexColor("#f3f4f6")
    border_color = colors.HexColor("#d1d5db")

    # -- Custom Styles --
    company_name_style = ParagraphStyle(
        "CompanyName",
        parent=styles["Normal"],
        fontSize=14,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
        leading=18,
    )

    company_info_style = ParagraphStyle(
        "CompanyInfo",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
        leading=14,
        alignment=TA_RIGHT,
    )

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=28,
        textColor=primary_color,
        spaceAfter=2 * mm,
        alignment=TA_LEFT,
    )

    subtitle_style = ParagraphStyle(
        "InvoiceSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=6 * mm,
    )

    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
    )

    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#111827"),
        fontName="Helvetica-Bold",
    )

    # ===== INVOICE TITLE WITH COMPANY INFO ON RIGHT =====
    company_info_text = (
        '<b>PT ASTON SISTEM INDONESIA</b><br/>'
        'Jl Imam Bonjol 28 Salatiga, 50714<br/>'
        '+62 298326431<br/>'
        'www.astonsistem.com'
    )

    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=20 * mm, height=20 * mm)
        logo.hAlign = "RIGHT"
    else:
        logo = ""

    # Combine invoice title with company info
    title_header_data = [[
        Paragraph("INVOICE", title_style),
        Paragraph(company_info_text, company_info_style),
        logo,
    ]]

    title_header = Table(title_header_data, colWidths=[70 * mm, 75 * mm, 25 * mm])
    title_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("RIGHTPADDING", (1, 0), (1, 0), 4 * mm),
        ("RIGHTPADDING", (2, 0), (2, 0), 0),
    ]))
    elements.append(title_header)
    elements.append(Paragraph(f"#{order.order_number}", subtitle_style))

    # ===== ORDER INFO =====
    info_data = [
        [
            Paragraph("Order Date", label_style),
            Paragraph("Status", label_style),
            Paragraph("MOU Number", label_style),
        ],
        [
            Paragraph(order.order_date.strftime("%d %B %Y"), value_style),
            Paragraph(
                order.status.name.replace("_", " ").title() if order.status else "-",
                value_style,
            ),
            Paragraph(order.mou.no_mou if order.mou else "-", value_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[60 * mm, 50 * mm, 60 * mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 6 * mm))

    # ===== CUSTOMER INFO =====
    customer = order.customer
    customer_data = [
        [Paragraph("Bill To", label_style), Paragraph("Customer Type", label_style)],
        [
            Paragraph(customer.name if customer else "-", value_style),
            Paragraph(customer.type if customer else "-", value_style),
        ],
    ]

    customer_table = Table(customer_data, colWidths=[100 * mm, 70 * mm])
    customer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(customer_table)
    elements.append(Spacer(1, 8 * mm))

    # ===== ITEMS TABLE =====
    header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontSize=9,
        textColor=header_text,
        fontName="Helvetica-Bold",
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#374151"),
    )

    cell_right_style = ParagraphStyle(
        "TableCellRight",
        parent=cell_style,
        alignment=TA_RIGHT,
    )

    header_right_style = ParagraphStyle(
        "TableHeaderRight",
        parent=header_style,
        alignment=TA_RIGHT,
    )

    table_data = [
        [
            Paragraph("No", header_style),
            Paragraph("Product", header_style),
            Paragraph("Qty", header_right_style),
            Paragraph("Unit Price", header_right_style),
            Paragraph("Subtotal", header_right_style),
        ]
    ]

    # Item rows
    for idx, detail in enumerate(order.order_details, 1):
        product_name = (
            detail.mou_product.product.product_name
            if detail.mou_product and detail.mou_product.product
            else "N/A"
        )
        table_data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(product_name, cell_style),
            Paragraph(str(detail.quantity), cell_right_style),
            Paragraph(f"Rp {detail.price:,.0f}", cell_right_style),
            Paragraph(f"Rp {detail.subtotal:,.0f}", cell_right_style),
        ])

    # Total row
    total_label_style = ParagraphStyle(
        "TotalLabel",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    )

    total_value_style = ParagraphStyle(
        "TotalValue",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=primary_color,
        alignment=TA_RIGHT,
    )

    table_data.append([
        "", "", "",
        Paragraph("TOTAL", total_label_style),
        Paragraph(f"Rp {order.total:,.0f}", total_value_style),
    ])

    col_widths = [12 * mm, 68 * mm, 20 * mm, 35 * mm, 35 * mm]
    items_table = Table(table_data, colWidths=col_widths)

    # Table styling
    num_items = len(order.order_details)
    table_style_commands = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), header_text),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        # All cells
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        # Grid for items
        ("GRID", (0, 0), (-1, num_items), 0.5, border_color),
        # Alternating row colors
        *[
            ("BACKGROUND", (0, i), (-1, i), light_gray)
            for i in range(2, num_items + 1, 2)
        ],
        # Total row
        ("LINEABOVE", (3, num_items + 1), (-1, num_items + 1), 1.5, primary_color),
        ("TOPPADDING", (0, num_items + 1), (-1, num_items + 1), 10),
    ]

    items_table.setStyle(TableStyle(table_style_commands))
    elements.append(items_table)
    elements.append(Spacer(1, 10 * mm))

    # ===== FOOTER =====
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#9ca3af"),
        alignment=TA_CENTER,
    )

    footer_lines = [
        f"Invoice generated on {datetime.now().strftime('%d %B %Y, %H:%M')}"
    ]
    if order.payment_confirmed_at:
        footer_lines.append(
            f"Payment confirmed on {order.payment_confirmed_at.strftime('%d %B %Y')}"
        )
    if order.completed_at:
        footer_lines.append(
            f"Order completed on {order.completed_at.strftime('%d %B %Y')}"
        )

    elements.append(Paragraph(" | ".join(footer_lines), footer_style))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return buffer
