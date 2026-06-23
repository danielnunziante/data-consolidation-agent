#!/usr/bin/env python3
"""Genera el PDF del instructivo de la API key a partir del Markdown.

El Markdown (`INSTRUCTIVO_API_KEY_OPENAI.md`) es la única fuente de verdad; este
script lo renderiza a PDF para entregarle al cliente.

Uso:
    pip install reportlab
    python3 docs/_build_instructivo_pdf.py

Sale: docs/INSTRUCTIVO_API_KEY_OPENAI.pdf
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).resolve().parent
MD = HERE / "INSTRUCTIVO_API_KEY_OPENAI.md"
PDF = HERE / "INSTRUCTIVO_API_KEY_OPENAI.pdf"

BRAND = colors.HexColor("#1f6feb")
INK = colors.HexColor("#1b1f24")
MUTED = colors.HexColor("#57606a")

# Quita emojis / símbolos fuera de Latin-1 (las fuentes estándar no los tienen).
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF️✅]",
    flags=re.UNICODE,
)


def _inline(text: str) -> str:
    """Convierte el inline de Markdown al mini-markup de reportlab."""
    text = _EMOJI.sub("", text).strip()
    # escapar XML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # `code`
    text = re.sub(r"`(.+?)`", r'<font face="Courier" size="9">\1</font>', text)
    # [texto](url)
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        r'<a href="\2" color="#1f6feb"><u>\1</u></a>',
        text,
    )
    # urls sueltas (que no quedaron dentro de un <a>)
    text = re.sub(
        r'(?<!")(?<!>)(https?://[^\s<]+)',
        r'<a href="\1" color="#1f6feb"><u>\1</u></a>',
        text,
    )
    return re.sub(r"\s{2,}", " ", text).strip()


def _callout(lines: list[str], styles) -> Table:
    body = " ".join(_inline(l) for l in lines if l.strip())
    low = body.lower()
    if "import" in low or "una sola vez" in low or "atenci" in low:
        bg, bar = colors.HexColor("#fff3cd"), colors.HexColor("#e0a800")
    elif "contraseña" in low or "no la compartas" in low or "seguridad" in low:
        bg, bar = colors.HexColor("#fde8e8"), colors.HexColor("#d1242f")
    else:
        bg, bar = colors.HexColor("#eef4ff"), BRAND
    p = Paragraph(body, styles["Callout"])
    t = Table([[p]], colWidths=[16.2 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3, bar),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def build() -> None:
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=22, textColor=INK, spaceAfter=6, leading=26),
        "H2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=14, textColor=BRAND, spaceBefore=16, spaceAfter=6, leading=18),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=10.5, textColor=INK, leading=15, spaceAfter=5, alignment=TA_LEFT),
        "Item": ParagraphStyle("Item", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=10.5, textColor=INK, leading=15),
        "Callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName="Helvetica",
                                  fontSize=10, textColor=INK, leading=14),
    }

    lines = MD.read_text(encoding="utf-8").splitlines()
    story: list = []
    i = 0
    pending_items: list = []
    ordered = False
    para_buf: list = []

    def flush_para():
        nonlocal para_buf
        if para_buf:
            story.append(Paragraph(_inline(" ".join(para_buf)), styles["Body"]))
            para_buf = []

    def flush_items():
        nonlocal pending_items, ordered
        if not pending_items:
            return
        story.append(
            ListFlowable(
                [ListItem(Paragraph(t, styles["Item"]), leftIndent=10) for t in pending_items],
                bulletType="1" if ordered else "bullet",
                bulletColor=BRAND,
                bulletFontName="Helvetica-Bold",
                leftIndent=18,
                spaceAfter=6,
            )
        )
        pending_items = []

    def flush_all():
        flush_para()
        flush_items()

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        m_ol = re.match(r"^\d+\.\s+(.*)", line)
        m_ul = re.match(r"^[-*]\s+(.*)", line)
        indented_cont = bool(raw[:1] in (" ", "\t")) and line.strip() != ""

        # Línea de continuación (indentada) -> se pega al último ítem o párrafo.
        if indented_cont and (pending_items or para_buf):
            if pending_items:
                pending_items[-1] += " " + _inline(line.strip())
            else:
                para_buf.append(line.strip())
            i += 1
            continue

        if line.startswith("> "):
            flush_all()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            story.append(Spacer(1, 4))
            story.append(_callout(buf, styles))
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            flush_all()
            story.append(Paragraph(_inline(line[2:]), styles["Title"]))
            story.append(HRFlowable(width="100%", thickness=2, color=BRAND, spaceAfter=10))
        elif line.startswith("## "):
            flush_all()
            story.append(Paragraph(_inline(line[3:]), styles["H2"]))
        elif line.startswith("### "):
            flush_all()
            story.append(Paragraph(_inline(line[4:]), styles["H2"]))
        elif line.strip() == "---":
            flush_all()
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#d0d7de")))
            story.append(Spacer(1, 4))
        elif m_ol:
            flush_para()
            if not ordered:
                flush_items()
            ordered = True
            pending_items.append(_inline(m_ol.group(1)))
        elif m_ul:
            flush_para()
            if ordered:
                flush_items()
            ordered = False
            pending_items.append(_inline(m_ul.group(1)))
        elif line.strip() == "":
            flush_all()
            story.append(Spacer(1, 3))
        else:
            flush_items()
            para_buf.append(line.strip())
        i += 1
    flush_all()

    doc = SimpleDocTemplate(
        str(PDF), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title="Instructivo - API Key de OpenAI", author="Consolidador de Cuentas Corrientes",
    )
    doc.build(story)
    print("PDF generado:", PDF)


if __name__ == "__main__":
    build()
