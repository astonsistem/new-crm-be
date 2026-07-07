import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# Logo and signature paths
LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "aston_logo.png")
SIGNATURE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "signature.png")


def _device_display(mou_device) -> tuple[str, str]:
    if not mou_device or not mou_device.serial_number:
        return "-", "-"

    asset = mou_device.serial_number.asset
    device_name = asset.asset_name if asset else "-"
    serial_number = mou_device.serial_number.serial_code or "-"
    return device_name, serial_number


def _resolve_detail_device(detail, mou_devices: list, line_index: int) -> tuple[str, str]:
    device_name = detail.device_name
    serial_number = detail.serial_number

    if device_name and serial_number:
        return device_name, serial_number

    if mou_devices:
        device = (
            mou_devices[0]
            if len(mou_devices) == 1
            else mou_devices[min(line_index, len(mou_devices) - 1)]
        )
        fallback_name, fallback_serial = _device_display(device)
        device_name = device_name or fallback_name
        serial_number = serial_number or fallback_serial

    return device_name or "-", serial_number or "-"


def build_bast_pdf(order, mou_devices: list | None = None) -> io.BytesIO:
    """
    Build a BAST (Berita Acara Serah Terima) PDF for the given order.

    Args:
        order: Order_Customer object with loaded relationships
              (mou, customer, order_details.mou_product.product)

    Returns:
        BytesIO buffer containing the PDF data
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # -- Colors --
    primary_color = colors.HexColor("#1a3a6b")
    header_bg = colors.HexColor("#1a3a6b")
    header_text = colors.white
    border_color = colors.HexColor("#333333")

    # -- Custom Styles --
    company_info_style = ParagraphStyle(
        "CompanyInfo",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13,
    )

    title_style = ParagraphStyle(
        "BASTTitle",
        parent=styles["Normal"],
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=primary_color,
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
        underline=True,
    )

    subtitle_style = ParagraphStyle(
        "BASTSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=primary_color,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )

    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
    )

    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#1f2937"),
    )

    normal_style = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13,
    )

    small_style = ParagraphStyle(
        "SmallText",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
        leading=11,
    )

    # ===== COMPANY HEADER WITH LOGO =====
    company_info_text = (
        '<b>PT ASTON SISTEM INDONESIA</b><br/>'
        'Jl Imam Bonjol 28 Salatiga, 50714<br/>'
        '+62 298326431<br/>'
        'www.astonsistem.com'
    )

    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=22 * mm, height=22 * mm)
        logo.hAlign = "LEFT"
    else:
        logo = ""

    company_header_data = [[
        logo,
        Paragraph(company_info_text, company_info_style),
    ]]

    company_header = Table(company_header_data, colWidths=[28 * mm, 140 * mm])
    company_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 4 * mm),
    ]))
    elements.append(company_header)
    elements.append(Spacer(1, 6 * mm))

    # ===== HORIZONTAL LINE =====
    line_table = Table([[""]], colWidths=[170 * mm])
    line_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 5 * mm))

    # ===== BAST TITLE =====
    elements.append(Paragraph("<u>BERITA ACARA SERAH TERIMA</u>", title_style))

    # Generate BAST number from order number
    bast_number = f"BAST-INK/{order.order_number}/{datetime.now().strftime('%Y')}"
    elements.append(Paragraph(bast_number, subtitle_style))

    # ===== CUSTOMER INFO =====
    customer = order.customer
    customer_name = customer.name if customer else "-"

    # Build pembelanjaan (items summary)
    item_names = []
    for detail in order.order_details:
        if detail.mou_product and detail.mou_product.product:
            item_names.append(detail.mou_product.product.product_name)
    pembelanjaan = ", ".join(item_names) if item_names else "-"

    info_data = [
        [
            Paragraph("Konsumen", label_style),
            Paragraph(f": {customer_name}", value_style),
        ],
        [
            Paragraph("Pembelanjaan", label_style),
            Paragraph(f": {pembelanjaan}", value_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[35 * mm, 135 * mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5 * mm))

    # ===== ITEMS TABLE =====
    header_style_table = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontSize=9,
        textColor=header_text,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#374151"),
    )

    cell_center_style = ParagraphStyle(
        "TableCellCenter",
        parent=cell_style,
        alignment=TA_CENTER,
    )

    table_data = [
        [
            Paragraph("No", header_style_table),
            Paragraph("Nama Barang", header_style_table),
            Paragraph("Nama Device", header_style_table),
            Paragraph("Serial Number", header_style_table),
            Paragraph("Keterangan", header_style_table),
        ]
    ]

    # Item rows - read device_name and serial_number from order details
    mou_devices = mou_devices or []
    for idx, detail in enumerate(order.order_details, 1):
        product_name = (
            detail.mou_product.product.product_name
            if detail.mou_product and detail.mou_product.product
            else "N/A"
        )
        device_name, serial_number = _resolve_detail_device(detail, mou_devices, idx - 1)
        keterangan = f"{detail.quantity} PCS Tinta Isi Ulang" if "consumables" in product_name.lower() else f"{detail.quantity} PCS"

        table_data.append([
            Paragraph(str(idx), cell_center_style),
            Paragraph(product_name, cell_style),
            Paragraph(device_name, cell_style),
            Paragraph(serial_number, cell_style),
            Paragraph(keterangan, cell_style),
        ])

    col_widths = [12 * mm, 48 * mm, 38 * mm, 38 * mm, 34 * mm]
    items_table = Table(table_data, colWidths=col_widths)

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
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, border_color),
    ]

    items_table.setStyle(TableStyle(table_style_commands))
    elements.append(items_table)
    elements.append(Spacer(1, 5 * mm))

    # ===== RECEPTION DATE =====
    elements.append(Paragraph(
        "Penerimaan tinta printer diatas dilakukan pada tanggal .......................................",
        normal_style
    ))
    elements.append(Spacer(1, 4 * mm))

    # ===== TERMS & CONDITIONS =====
    terms_title_style = ParagraphStyle(
        "TermsTitle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=2 * mm,
    )

    terms_style = ParagraphStyle(
        "Terms",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13,
        leftIndent=5 * mm,
    )

    elements.append(Paragraph("Syarat Ketentuan :", terms_title_style))

    terms = [
        "Status unit printer Sewa.",
        "Kerusakan yang terjadi pada unit printer ini menjadi tanggung jawab PT. Aston Sistem Indonesia.",
        "Bahan habis pakai tidak di buang melainkan dijadikan satu yang nantinya akan diambil oleh tim dari PT. Aston Sistem Indonesia saat kunjungan maintenance.",
        "Maintenance rutin dilakukan setiap 6-12 bulan sekali.",
        "Tidak boleh menggunakan tinta merek lain.",
        "Kardus printer tidak boleh dibuang.",
        "Informasi lebih lanjut terkait Unit Printer Sewa PT. Aston Sistem Indonesia bisa menghubungi :",
    ]

    for i, term in enumerate(terms, 1):
        elements.append(Paragraph(f"{i}.&nbsp;&nbsp;{term}", terms_style))

    elements.append(Spacer(1, 3 * mm))

    # ===== CONTACT INFO =====
    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13,
        leftIndent=10 * mm,
    )

    contact_data = [
        [
            Paragraph(
                "Nama&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: Roby<br/>"
                "Jabatan&nbsp;&nbsp;&nbsp;: Technical Support<br/>"
                "Nomor&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: 0896-9696-9685",
                contact_style
            ),
            Paragraph(
                "Nama&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: Taufiqurrahman<br/>"
                "Jabatan&nbsp;&nbsp;&nbsp;: Account Manager<br/>"
                "Nomor&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: 0813-8585-4715",
                contact_style
            ),
        ]
    ]

    contact_table = Table(contact_data, colWidths=[85 * mm, 85 * mm])
    contact_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(contact_table)
    elements.append(Spacer(1, 8 * mm))

    # ===== SIGNATURE SECTION =====
    sig_header_style = ParagraphStyle(
        "SigHeader",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#333333"),
        alignment=TA_CENTER,
    )

    sig_name_style = ParagraphStyle(
        "SigName",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
        alignment=TA_CENTER,
    )

    sig_company_style = ParagraphStyle(
        "SigCompany",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f2937"),
        alignment=TA_CENTER,
    )

    # Create signature image if exists
    if os.path.exists(SIGNATURE_PATH):
        signature_img = Image(SIGNATURE_PATH, width=60 * mm, height=40 * mm)
        signature_img.hAlign = "CENTER"
    else:
        signature_img = Paragraph(".......................................", sig_header_style)

    sig_data = [
        [
            Paragraph("Penerima", sig_header_style),
            Paragraph("Pengirim", sig_header_style),
        ],
        [
            Paragraph(f"{customer_name}", sig_name_style),
            signature_img,  # Signature image aligned with customer name
        ],
        [
            Paragraph(".......................................", sig_header_style),
            Paragraph("", sig_header_style),
        ],
        [
            Paragraph("", sig_header_style),
            Paragraph("", sig_header_style),
        ],
    ]

    sig_table = Table(sig_data, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),  # Changed back to TOP for better alignment
        ("VALIGN", (1, 1), (1, 1), "MIDDLE"),  # Make signature image cell middle-aligned
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 8 * mm))

    # ===== NOTE (NB) =====
    nb_style = ParagraphStyle(
        "NB",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
        leading=11,
    )

    nb_highlight_style = ParagraphStyle(
        "NBHighlight",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.red,
        leading=11,
    )

    elements.append(Paragraph(
        'NB : &nbsp;&nbsp;Mohon dilengkapi <font color="red"><b>Nama Gerai, TTD dan Stempel</b></font> '
        'kemudian foto dokumen dikirim ke :',
        nb_style
    ))
    elements.append(Paragraph(
        '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        'WA (0813-8585-4715) / Email (taufiqurahman@astonsistem.com), Terimakasih',
        nb_style
    ))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return buffer
