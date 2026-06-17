"""Helpers for Excel export formatting."""

from openpyxl.styles import Border, Side

_THIN = Side(style="thin")
ALL_BORDERS = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def format_worksheet(worksheet) -> None:
    """Apply all borders and auto-fit column widths."""
    for row in worksheet.iter_rows():
        for cell in row:
            cell.border = ALL_BORDERS

    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if cell.value is not None and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
