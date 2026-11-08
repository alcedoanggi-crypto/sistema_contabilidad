"""Exporta cualquier reporte tabular a PDF (ReportLab) o Excel (openpyxl)."""
import io
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1e3a5f")


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:,.2f}"
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m/%Y")
    return str(v)


def a_pdf(titulo: str, subtitulo: str, empresa: str, columnas: list[str], renglones: list[list],
          totales: list | None = None, numericas: set[int] = frozenset(), horizontal: bool = False,
          negritas: set[int] = frozenset()) -> bytes:
    buf = io.BytesIO()
    tam = landscape(A4) if horizontal else A4
    doc = SimpleDocTemplate(buf, pagesize=tam, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=titulo)
    est_emp = ParagraphStyle("e", fontName="Helvetica-Bold", fontSize=13, textColor=AZUL)
    est_tit = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=11, spaceBefore=2)
    est_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#555555"))
    est_celda = ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)

    datos = [columnas]
    for r in renglones:
        datos.append([Paragraph(_texto(v), est_celda) if i not in numericas else _texto(v) for i, v in enumerate(r)])
    if totales:
        datos.append([_texto(v) for v in totales])

    ancho = tam[0] - 28 * mm
    tabla = Table(datos, repeatRows=1, colWidths=_anchos(columnas, numericas, ancho))
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7e2")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in numericas:
        estilo.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
    for k in negritas:
        estilo.append(("FONTNAME", (0, k + 1), (-1, k + 1), "Helvetica-Bold"))
    if totales:
        estilo += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                   ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2f7")),
                   ("LINEABOVE", (0, -1), (-1, -1), 1, AZUL)]
    tabla.setStyle(TableStyle(estilo))

    def pie(canvas, d):
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(14 * mm, 8 * mm, f"Generado el {datetime.now():%d/%m/%Y %H:%M}")
        canvas.drawRightString(tam[0] - 14 * mm, 8 * mm, f"Página {d.page}")

    doc.build([Paragraph(empresa, est_emp), Paragraph(titulo, est_tit), Paragraph(subtitulo, est_sub),
               Spacer(1, 5 * mm), tabla], onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()


def _anchos(columnas, numericas, ancho):
    pesos = [1.0 if i in numericas else (2.6 if i in (1,) else 1.3) for i in range(len(columnas))]
    total = sum(pesos)
    return [ancho * p / total for p in pesos]


def a_excel(titulo: str, subtitulo: str, empresa: str, columnas: list[str], renglones: list[list],
            totales: list | None = None, numericas: set[int] = frozenset(), negritas: set[int] = frozenset()) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31]
    ws.append([empresa])
    ws.append([titulo])
    ws.append([subtitulo])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=13, color="1E3A5F")
    ws["A2"].font = Font(bold=True, size=11)
    ws["A3"].font = Font(italic=True, color="555555")
    ws.append(columnas)
    cab = 5
    for c in ws[cab]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E3A5F")
        c.alignment = Alignment(horizontal="center")
    for k, r in enumerate(renglones):
        ws.append([float(v) if isinstance(v, Decimal) else v for v in r])
        if k in negritas:
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
    if totales:
        ws.append([float(v) if isinstance(v, Decimal) else v for v in totales])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="EEF2F7")
            c.border = Border(top=Side(style="thin", color="1E3A5F"))
    for fila_ in ws.iter_rows(min_row=cab + 1):
        for i, c in enumerate(fila_):
            if i in numericas:
                c.number_format = "#,##0.00"
            elif isinstance(c.value, (date, datetime)):
                c.number_format = "DD/MM/YYYY"
    for i, col in enumerate(columnas, start=1):
        largo = max([len(str(col))] + [len(_texto(r[i - 1])) for r in renglones[:500]])
        ws.column_dimensions[ws.cell(row=cab, column=i).column_letter].width = min(max(10, largo + 2), 60)
    ws.freeze_panes = ws.cell(row=cab + 1, column=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
