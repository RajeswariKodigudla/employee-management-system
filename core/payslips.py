from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .models import PayrollRecord


FONT_NAME = "PayslipUnicode"
RUPEE_CODEPOINT = 0x20B9


def _register_payslip_font():
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return

    configured_path = getattr(settings, "PAYSLIP_FONT_PATH", None)
    font_paths = (
        [Path(configured_path)]
        if configured_path
        else [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        ]
    )

    for font_path in font_paths:
        if not font_path.is_file():
            continue
        font = TTFont(FONT_NAME, str(font_path))
        if RUPEE_CODEPOINT in font.face.charToGlyph:
            pdfmetrics.registerFont(font)
            return

    raise ImproperlyConfigured(
        "A TrueType font containing the Indian rupee symbol is required for "
        "payslip PDFs. Set PAYSLIP_FONT_PATH to a suitable .ttf font file."
    )


def format_currency(amount):
    return f"\u20b9{amount:,.2f}"


def payslip_values(record: PayrollRecord):
    return {
        "company_name": getattr(
            settings,
            "PAYSLIP_COMPANY_NAME",
            "Employee Management System",
        ),
        "employee_name": record.employee.full_name,
        "employee_id": record.employee.employee_id,
        "department": record.employee.department.name,
        "designation": record.employee.designation,
        "pay_month": record.pay_month.strftime("%B %Y"),
        "payment_status": record.get_payment_status_display().upper(),
        "payment_date": (
            record.payment_date.strftime("%d %B %Y")
            if record.payment_date
            else "Not recorded"
        ),
        "basic_salary": format_currency(record.basic_salary),
        "allowances": format_currency(record.allowances),
        "gross_salary": format_currency(record.gross_salary),
        "deductions": format_currency(record.deductions),
        "net_salary": format_currency(record.net_salary),
    }


def generate_payslip_pdf(record: PayrollRecord) -> bytes:
    _register_payslip_font()
    values = payslip_values(record)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_width, page_height = A4
    purple = colors.HexColor("#6658d3")
    ink = colors.HexColor("#202238")
    muted = colors.HexColor("#74788f")
    pale = colors.HexColor("#f5f4ff")

    pdf.setTitle(f"Payslip - {values['employee_name']} - {values['pay_month']}")
    pdf.setAuthor(values["company_name"])

    pdf.setFillColor(purple)
    pdf.rect(0, page_height - 132, page_width, 132, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont(FONT_NAME, 11)
    pdf.drawString(48, page_height - 43, values["company_name"])
    pdf.setFont(FONT_NAME, 24)
    pdf.drawString(48, page_height - 82, "PAYSLIP")
    pdf.setFont(FONT_NAME, 11)
    pdf.drawRightString(page_width - 48, page_height - 76, values["pay_month"])

    pdf.setFillColor(ink)
    pdf.setFont(FONT_NAME, 14)
    pdf.drawString(48, page_height - 174, values["employee_name"])

    status_color = (
        colors.HexColor("#16876a")
        if record.payment_status == "PAID"
        else colors.HexColor("#c77b25")
        if record.payment_status in ("PENDING", "ON_HOLD")
        else muted
    )
    badge_width = pdfmetrics.stringWidth(values["payment_status"], FONT_NAME, 9) + 22
    pdf.setFillColor(status_color)
    pdf.roundRect(page_width - 48 - badge_width, page_height - 185, badge_width, 25, 7, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont(FONT_NAME, 9)
    pdf.drawCentredString(
        page_width - 48 - badge_width / 2,
        page_height - 176,
        values["payment_status"],
    )

    pdf.setFillColor(pale)
    pdf.roundRect(48, page_height - 300, page_width - 96, 94, 10, fill=1, stroke=0)
    details = [
        ("Employee ID", values["employee_id"]),
        ("Department", values["department"]),
        ("Designation", values["designation"]),
        ("Payment date", values["payment_date"]),
    ]
    detail_positions = [
        (64, page_height - 234),
        (300, page_height - 234),
        (64, page_height - 276),
        (300, page_height - 276),
    ]
    for (label, value), (x, y) in zip(details, detail_positions):
        pdf.setFillColor(muted)
        pdf.setFont(FONT_NAME, 8)
        pdf.drawString(x, y + 13, label.upper())
        pdf.setFillColor(ink)
        pdf.setFont(FONT_NAME, 10)
        pdf.drawString(x, y, value)

    pdf.setFillColor(ink)
    pdf.setFont(FONT_NAME, 13)
    pdf.drawString(48, page_height - 345, "Salary breakdown")
    pdf.setStrokeColor(colors.HexColor("#e6e6ef"))
    pdf.line(48, page_height - 357, page_width - 48, page_height - 357)

    rows = [
        ("Basic salary", values["basic_salary"], False),
        ("Allowances", values["allowances"], False),
        ("Gross salary", values["gross_salary"], True),
        ("Deductions", values["deductions"], False),
        ("Net salary", values["net_salary"], True),
    ]
    y = page_height - 390
    for label, amount, emphasized in rows:
        if emphasized:
            pdf.setFillColor(pale if label == "Gross salary" else purple)
            pdf.roundRect(48, y - 10, page_width - 96, 34, 6, fill=1, stroke=0)
        pdf.setFillColor(colors.white if label == "Net salary" else ink)
        pdf.setFont(FONT_NAME, 11 if emphasized else 10)
        pdf.drawString(62, y + 1, label)
        pdf.drawRightString(page_width - 62, y + 1, amount)
        y -= 49

    pdf.setFillColor(muted)
    pdf.setFont(FONT_NAME, 8)
    pdf.drawCentredString(
        page_width / 2,
        44,
        "This payslip reflects the payroll record stored in the system.",
    )
    pdf.showPage()
    pdf.save()
    return output.getvalue()
