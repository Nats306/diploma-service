"""
Genera el PDF del diploma. Sin dependencias externas de red: todo se
dibuja con reportlab. La "firma digital" es un sello/firma visual
(nombre + linea), no una firma criptografica del archivo.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

AZUL = HexColor("#0056D2")
GRIS = HexColor("#5B6670")
NEGRO = HexColor("#1F1F1F")

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def formatear_fecha_es(fecha):
    """Formatea una fecha en español sin depender del locale del sistema
    (que en un contenedor casi nunca tiene es_ES instalado)."""
    if fecha is None:
        return ""
    if isinstance(fecha, str):
        return fecha
    return f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"


def _centered(c, text, y, font="Helvetica", size=12, color=NEGRO):
    page_w, _ = c._pagesize
    w = stringWidth(text, font, size)
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString((page_w - w) / 2.0, y, text)


def generar_diploma_pdf(nombre_completo, curso_nombre, fecha_inscripcion, curso_id=""):
    """Devuelve los bytes de un PDF de una sola pagina, tamano carta horizontal."""
    buf = io.BytesIO()
    page_w, page_h = landscape(letter)
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # Borde decorativo doble
    margin = 1.1 * cm
    c.setStrokeColor(AZUL)
    c.setLineWidth(3)
    c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)
    c.setLineWidth(0.75)
    c.rect(margin + 0.25 * cm, margin + 0.25 * cm,
           page_w - 2 * margin - 0.5 * cm, page_h - 2 * margin - 0.5 * cm)

    # Marca / titulo
    _centered(c, "coursera", page_h - 3.0 * cm, font="Helvetica-Bold", size=22, color=AZUL)
    _centered(c, "CERTIFICADO DE FINALIZACIÓN", page_h - 4.3 * cm,
              font="Helvetica-Bold", size=15, color=GRIS)

    _centered(c, "Se certifica que", page_h - 6.0 * cm, font="Helvetica", size=13, color=GRIS)

    _centered(c, nombre_completo, page_h - 7.3 * cm,
              font="Helvetica-Bold", size=26, color=NEGRO)

    # linea bajo el nombre
    name_w = stringWidth(nombre_completo, "Helvetica-Bold", 26)
    line_w = max(name_w + 3 * cm, 10 * cm)
    c.setStrokeColor(AZUL)
    c.setLineWidth(1)
    c.line((page_w - line_w) / 2.0, page_h - 7.7 * cm,
           (page_w + line_w) / 2.0, page_h - 7.7 * cm)

    _centered(c, "ha completado satisfactoriamente el curso", page_h - 8.9 * cm,
              font="Helvetica", size=13, color=GRIS)
    _centered(c, curso_nombre, page_h - 10.0 * cm,
              font="Helvetica-Bold", size=18, color=AZUL)

    # Fecha
    if isinstance(fecha_inscripcion, str):
        fecha_txt = fecha_inscripcion
    else:
        fecha_txt = formatear_fecha_es(fecha_inscripcion or datetime.utcnow())
    _centered(c, f"Fecha: {fecha_txt}", page_h - 11.2 * cm,
              font="Helvetica-Oblique", size=11, color=GRIS)

    # ---- Firma (sello visual) ----
    sig_y = margin + 2.6 * cm
    sig_x_center = page_w - 8.0 * cm
    c.setFont("Helvetica-Oblique", 20)
    c.setFillColor(AZUL)
    sig_text = "Coursera Clone"
    sig_w = stringWidth(sig_text, "Helvetica-Oblique", 20)
    c.drawString(sig_x_center - sig_w / 2.0, sig_y + 0.4 * cm, sig_text)
    c.setStrokeColor(NEGRO)
    c.setLineWidth(0.75)
    c.line(sig_x_center - 4 * cm, sig_y, sig_x_center + 4 * cm, sig_y)
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    firma_label = "Firma digital — Equipo Coursera Clone"
    label_w = stringWidth(firma_label, "Helvetica", 9)
    c.drawString(sig_x_center - label_w / 2.0, sig_y - 0.5 * cm, firma_label)

    # ---- Sello de verificación (curso_id) ----
    if curso_id:
        c.setFont("Helvetica", 8)
        c.setFillColor(GRIS)
        c.drawString(margin + 0.6 * cm, margin + 0.6 * cm, f"ID de verificación: {curso_id}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    pdf_bytes = generar_diploma_pdf(
        "Nate Mejia",
        "Python for Everybody",
        "20 de septiembre de 2026",
        curso_id="entryId123",
    )
    with open("/tmp/diploma-service/diploma_test.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("PDF generado:", len(pdf_bytes), "bytes")
