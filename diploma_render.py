"""
Genera el PDF del diploma. Sin dependencias externas de red: todo se
dibuja con reportlab (mas Pillow, solo para renderizar la firma en
letra script como una imagen). La "firma digital" es un sello/firma
visual (nombre + linea), no una firma criptografica del archivo.

Diseno inspirado en el formato clasico de certificado tipo Coursera:
logo arriba a la izquierda, cinta "VERIFIED CERTIFICATE" con sello
arriba a la derecha, bloque de texto alineado a la izquierda (fecha,
nombre, curso), firma abajo a la izquierda y datos de verificacion
abajo a la derecha.
"""
import io
import os
import math
from datetime import datetime

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageFont, ImageDraw

AZUL = HexColor("#0056D2")
AZUL_OSCURO = HexColor("#00369F")
GRIS = HexColor("#5B6670")
GRIS_CLARO = HexColor("#8A94A0")
NEGRO = HexColor("#1A1A1A")
NARANJA = HexColor("#B45309")
CINTA_FONDO = HexColor("#EDF1F8")
CINTA_BORDE = HexColor("#C7D3E6")

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FIRMA_FONT_PATH = os.path.join(FONTS_DIR, "DancingScript-Bold.otf")


def formatear_fecha_es(fecha):
    """Formatea una fecha en espanol sin depender del locale del sistema
    (que en un contenedor casi nunca tiene es_ES instalado)."""
    if fecha is None:
        return ""
    if isinstance(fecha, str):
        return fecha
    return f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"


def _render_firma_png(texto, font_path=FIRMA_FONT_PATH, size_px=90, color=(26, 26, 26, 255)):
    """Dibuja `texto` con una tipografia script (via Pillow/FreeType) y
    devuelve los bytes PNG con fondo transparente. Se usa como imagen
    dentro del PDF porque reportlab no puede incrustar directamente las
    fuentes OpenType/CFF de Google Fonts (solo TrueType 'glyf')."""
    font = ImageFont.truetype(font_path, size_px)
    # Lienzo de sobra, luego se recorta al bounding box real del texto.
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), texto, font=font)
    pad = 12
    w = (bbox[2] - bbox[0]) + pad * 2
    h = (bbox[3] - bbox[1]) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad - bbox[0], pad - bbox[1]), texto, font=font, fill=color)
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out, w, h


def _text_with_spacing(c, text, x, y, font, size, color, char_space=0.0):
    # OJO: el espaciado entre caracteres (Tc) es parte del estado grafico
    # de texto en PDF y persiste entre bloques BT/ET hasta que se vuelve
    # a fijar -- si no se resetea a 0 aqui, TODO el texto dibujado
    # despues (fechas, nombre, curso, pie de pagina...) hereda este
    # espaciado extra y termina desbordandose de la pagina.
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setFillColor(color)
    if char_space:
        t.setCharSpace(char_space)
    t.textLine(text)
    if char_space:
        t.setCharSpace(0)
    c.drawText(t)


def _star_path(c, cx, cy, r_outer, r_inner, color):
    p = c.beginPath()
    points = []
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        ang = math.pi / 2 + i * math.pi / 5
        points.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    p.moveTo(*points[0])
    for pt in points[1:]:
        p.lineTo(*pt)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, fill=1, stroke=0)


def _draw_ribbon(c, page_w, page_h, margin):
    """Cinta vertical arriba a la derecha con texto 'VERIFIED
    CERTIFICATE' y un sello circular punteado debajo, como en los
    certificados clasicos de Coursera."""
    ribbon_w = 2.5 * cm
    ribbon_top = page_h - margin
    ribbon_flat_bottom = ribbon_top - 6.1 * cm
    tip_depth = 0.9 * cm
    notch_depth = 0.35 * cm

    rx0 = page_w - margin - 3.1 * cm
    rx1 = rx0 + ribbon_w
    mid = (rx0 + rx1) / 2.0

    path = c.beginPath()
    path.moveTo(rx0, ribbon_top)
    path.lineTo(rx1, ribbon_top)
    path.lineTo(rx1, ribbon_flat_bottom - tip_depth)
    path.lineTo(mid, ribbon_flat_bottom - notch_depth)
    path.lineTo(rx0, ribbon_flat_bottom - tip_depth)
    path.close()

    c.setFillColor(CINTA_FONDO)
    c.setStrokeColor(CINTA_BORDE)
    c.setLineWidth(0.75)
    c.drawPath(path, fill=1, stroke=1)

    _text_with_spacing(c, "VERIFIED", mid - 0.95 * cm, ribbon_top - 1.05 * cm,
                        "Helvetica-Bold", 7.5, GRIS, char_space=1.1)
    _text_with_spacing(c, "CERTIFICATE", mid - 1.35 * cm, ribbon_top - 1.55 * cm,
                        "Helvetica-Bold", 7.5, GRIS, char_space=1.1)

    seal_cy = ribbon_top - 3.5 * cm
    c.setStrokeColor(CINTA_BORDE)
    c.setDash(1, 2)
    c.setLineWidth(1.1)
    c.circle(mid, seal_cy, 1.05 * cm, stroke=1, fill=0)
    c.setDash()
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.2)
    c.circle(mid, seal_cy, 0.82 * cm, stroke=1, fill=0)
    _star_path(c, mid, seal_cy, 0.42 * cm, 0.18 * cm, AZUL)


def generar_diploma_pdf(nombre_completo, curso_nombre, fecha_inscripcion, curso_id=""):
    """Devuelve los bytes de un PDF de una sola pagina, tamano carta horizontal."""
    buf = io.BytesIO()
    page_w, page_h = landscape(letter)
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    margin = 1.1 * cm
    content_x = margin + 1.4 * cm

    # Borde simple
    c.setStrokeColor(HexColor("#B9C2CE"))
    c.setLineWidth(1.2)
    c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)

    # ---- Logo (marca de la plataforma) ----
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(AZUL)
    c.drawString(content_x, page_h - margin - 1.35 * cm, "coursera")

    # ---- Cinta + sello ----
    _draw_ribbon(c, page_w, page_h, margin)

    # ---- Fecha ----
    if isinstance(fecha_inscripcion, str) and fecha_inscripcion:
        fecha_txt = fecha_inscripcion
    else:
        fecha_txt = formatear_fecha_es(fecha_inscripcion or datetime.utcnow())
    y = page_h - margin - 3.4 * cm
    c.setFont("Helvetica", 11)
    c.setFillColor(NARANJA)
    c.drawString(content_x, y, fecha_txt)

    # ---- Nombre ----
    y -= 1.15 * cm
    c.setFont("Times-Bold", 30)
    c.setFillColor(NEGRO)
    c.drawString(content_x, y, nombre_completo)

    # ---- "ha completado..." ----
    y -= 0.85 * cm
    c.setFont("Helvetica", 12.5)
    c.setFillColor(GRIS)
    c.drawString(content_x, y, "ha completado satisfactoriamente el curso")

    # ---- Curso ----
    y -= 0.95 * cm
    c.setFont("Times-Bold", 17)
    c.setFillColor(AZUL_OSCURO)
    c.drawString(content_x, y, curso_nombre)

    # ---- Firma (imagen renderizada con tipografia script) ----
    sig_x = content_x
    sig_line_y = margin + 2.1 * cm
    sig_line_w = 6.4 * cm

    firma_png, fw, fh = _render_firma_png("Equipo Coursera")
    disp_h = 1.5 * cm
    disp_w = disp_h * (fw / fh)
    c.drawImage(ImageReader(firma_png), sig_x, sig_line_y + 0.15 * cm,
                width=disp_w, height=disp_h, mask="auto")

    c.setStrokeColor(HexColor("#4A4A4A"))
    c.setLineWidth(0.75)
    c.line(sig_x, sig_line_y, sig_x + sig_line_w, sig_line_y)

    c.setFont("Helvetica", 9.5)
    c.setFillColor(GRIS)
    c.drawString(sig_x, sig_line_y - 0.45 * cm, "Coordinacion del programa — Coursera")

    # ---- Verificacion (abajo a la derecha) ----
    right_x = page_w - margin - 1.2 * cm
    verify_y = margin + 2.0 * cm
    verify_txt = f"Verifica en coursera.app/verificar/{curso_id}" if curso_id else \
        "Verifica este certificado con la plataforma"
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    w = stringWidth(verify_txt, "Helvetica", 9)
    c.drawString(right_x - w, verify_y, verify_txt)

    disclaimer = "Este certificado confirma la identidad del usuario y su participacion en el curso."
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(GRIS_CLARO)
    w = stringWidth(disclaimer, "Helvetica-Oblique", 7.5)
    c.drawString(right_x - w, verify_y - 0.4 * cm, disclaimer)

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
