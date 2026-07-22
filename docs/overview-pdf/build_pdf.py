#!/usr/bin/env python3
"""Build the 2-page, diagram-led EPM Wizard overview PDF."""
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak,
    HRFlowable,
)
from svglib.svglib import svg2rlg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "EPM-Wizard-Overview.pdf")

BLUE = HexColor("#0f62fe")
DARK = HexColor("#161616")
GRAY = HexColor("#525252")

MARGIN = 0.6 * inch
PAGE_W, PAGE_H = letter
AVAIL_W = PAGE_W - 2 * MARGIN

styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22,
                            leading=26, textColor=DARK, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10.5,
                               leading=14, textColor=GRAY, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12,
                         leading=15, textColor=BLUE, spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.3,
                           leading=12.6, textColor=DARK, spaceAfter=4),
    "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique",
                              fontSize=8, leading=10, textColor=GRAY,
                              spaceBefore=3),
}


def svg(name, width=AVAIL_W):
    drawing = svg2rlg(os.path.join(HERE, name))
    scale = min(1.0, width / drawing.width)
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    return drawing


story = []

# ---------------------------------------------------------------- page 1
story.append(Paragraph("EPM Wizard", styles["title"]))
story.append(Paragraph(
    "A local-first, ChatGPT-style AI workspace for Oracle EPM implementation.",
    styles["subtitle"]))
story.append(HRFlowable(width="100%", thickness=1.4, color=BLUE, spaceAfter=6))
story.append(Paragraph(
    "Build, validate, and deploy Oracle EPM artifacts from a chat interface. "
    "Runs entirely on your machine with <b>docker compose up</b> — zero config, "
    "no API key, IBM Carbon design.",
    styles["body"]))

story.append(Paragraph("What it does", styles["h2"]))
story.append(svg("tiles.svg"))

story.append(Paragraph("How a request becomes a deployed Oracle artifact", styles["h2"]))
story.append(svg("pipeline.svg"))

story.append(Paragraph("Security model", styles["h2"]))
story.append(svg("security.svg"))

story.append(PageBreak())

# ---------------------------------------------------------------- page 2
story.append(Paragraph("System architecture", styles["h2"]))
story.append(svg("arch.svg"))
story.append(Paragraph(
    "React SPA + FastAPI over SSE. Pydantic owns the canonical schemas — TypeScript "
    "and Zod are generated from them (a CI drift test enforces it). The connector "
    "boundary is the only path to Oracle.",
    styles["caption"]))

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(MARGIN, 0.38 * inch,
                      "EPM Wizard — independent implementation tool. IBM and Oracle product "
                      "names are trademarks of their respective owners.")
    canvas.drawRightString(PAGE_W - MARGIN, 0.38 * inch, f"Page {doc.page} of 2")
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
                      topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                      title="EPM Wizard — Overview & Architecture",
                      author="EPM Wizard")
frame = Frame(MARGIN, 0.55 * inch, AVAIL_W, PAGE_H - 1.1 * inch,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])
doc.build(story)
print("wrote", OUT)
