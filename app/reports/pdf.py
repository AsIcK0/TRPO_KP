"""Генерация PDF-отчетов (ReportLab) из данных БД. Для кириллицы нужен TTF-шрифт (DejaVu Sans)."""

import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",        # Debian/Ubuntu (fonts-dejavu-core)
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",      # AlmaLinux/Fedora
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
_FONT_NAME = "ReportFont"


@dataclass
class ReportData:
    title: str
    period: str
    generated_at: datetime
    generated_by: str
    columns: list[str]
    col_weights: list[float]
    rows: list[list[str]]
    filters: list[str] = field(default_factory=list)
    summary: list[tuple[str, str]] = field(default_factory=list)


def _find_font(configured: str | None) -> str:
    for path in ([configured] if configured else []) + list(_FONT_CANDIDATES):
        if path and os.path.isfile(path):
            return path
    raise RuntimeError("Не найден TTF-шрифт с кириллицей: установите fonts-dejavu-core или задайте PDF_FONT_PATH")


def _register_fonts(configured: str | None) -> tuple[str, str]:
    bold_name = f"{_FONT_NAME}-Bold"
    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        regular = _find_font(configured)
        bold = regular.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace("arial.ttf", "arialbd.ttf")
        if not os.path.isfile(bold):
            bold = regular
        pdfmetrics.registerFont(TTFont(_FONT_NAME, regular))
        pdfmetrics.registerFont(TTFont(bold_name, bold))
        pdfmetrics.registerFontFamily(_FONT_NAME, normal=_FONT_NAME, bold=bold_name)
    return _FONT_NAME, bold_name


def _fmt_dt(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def render_report(data: ReportData, font_path: str | None = None) -> bytes:
    regular, bold = _register_fonts(font_path)
    title_style = ParagraphStyle("title", fontName=bold, fontSize=15, leading=19, spaceAfter=4)
    meta_style = ParagraphStyle("meta", fontName=regular, fontSize=9, leading=12)
    cell_style = ParagraphStyle("cell", fontName=regular, fontSize=8, leading=10)
    head_style = ParagraphStyle("head", fontName=bold, fontSize=8, leading=10, textColor=colors.white)
    h2_style = ParagraphStyle("h2", fontName=bold, fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)

    def cell(text: str, style: ParagraphStyle = cell_style) -> Paragraph:
        return Paragraph(escape(text), style)

    page = landscape(A4)
    margin = 12 * mm
    width = page[0] - 2 * margin
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin + 4 * mm, title=data.title,
                            author="Система учета входящей корреспонденции")

    story: list = [Paragraph(escape(data.title), title_style),
                   Paragraph(f"Период: {escape(data.period)}", meta_style)]
    filters_text = "; ".join(data.filters) if data.filters else "не заданы"
    story.append(Paragraph(f"Фильтры: {escape(filters_text)}", meta_style))
    story.append(Paragraph(
        f"Дата формирования: {_fmt_dt(data.generated_at)}. Сформировал: {escape(data.generated_by)}", meta_style))
    story.append(Spacer(1, 6 * mm))

    if data.rows:
        total = sum(data.col_weights) or 1.0
        col_widths = [width * w / total for w in data.col_weights]
        table_data = [[cell(c, head_style) for c in data.columns]] + [[cell(v) for v in row] for row in data.rows]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F4B6E")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA5B1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F4F8")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Нет данных за выбранный период и заданные фильтры.", meta_style))

    if data.summary:
        story.append(Paragraph("Итоговые показатели", h2_style))
        summary_table = Table([[cell(k), cell(v)] for k, v in data.summary], colWidths=[width * 0.45, width * 0.2])
        summary_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA5B1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F4F8")),
        ]))
        story.append(summary_table)

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.drawRightString(page[0] - margin, 8 * mm, f"Стр. {document.page}")
        canvas.drawString(margin, 8 * mm, data.title)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
