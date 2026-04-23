"""Estilos y helpers de openpyxl para el workbook final."""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

HEADER_FILL = PatternFill(start_color="FF305496", end_color="FF305496", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

BODY_FONT = Font(name="Calibri", size=10)
BODY_ALIGN = Alignment(vertical="center")

THIN = Side(border_style="thin", color="FFBFBFBF")
HEADER_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

DATE_FMT = "yyyy-mm-dd"
MONEY_FMT = "#,##0.00;[Red]-#,##0.00"

# Anchos pensados para legibilidad
COLUMN_WIDTHS = {
    "FECHA": 12,
    "POLIZA": 22,
    "ASEGURADO": 42,
    "SECCION": 26,
    "COMPAÑÍA": 24,
    "TIPO": 8,
    "COMISIONES": 16,
    "PRIMA": 16,
    "PREMIO": 16,
    "COMPROBACION DE DUPLICADOS": 28,
    "Columna1": 12,
}
