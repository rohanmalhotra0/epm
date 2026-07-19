#!/usr/bin/env python3
"""Build the 2-page EPM Wizard overview PDF."""
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, PageBreak, HRFlowable,
)
from svglib.svglib import svg2rlg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "EPM-Wizard-Overview.pdf")

BLUE = HexColor("#0f62fe")
DARK = HexColor("#161616")
GRAY = HexColor("#525252")

MARGIN = 0.6 * inch
PAGE_W, PAGE_H = letter

styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22,
                            leading=26, textColor=DARK, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10.5,
                               leading=14, textColor=GRAY, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12,
                         leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10,
                         leading=13, textColor=DARK, spaceBefore=6, spaceAfter=2),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.3,
                           leading=12.6, textColor=DARK, alignment=TA_LEFT,
                           spaceAfter=4),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.3,
                             leading=12.4, textColor=DARK, leftIndent=12,
                             bulletIndent=2, spaceAfter=2.5),
    "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8.2,
                           leading=11, textColor=DARK, leftIndent=8,
                           spaceBefore=2, spaceAfter=4),
    "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique",
                              fontSize=8, leading=10, textColor=GRAY,
                              spaceBefore=2, spaceAfter=4),
    "tcell": ParagraphStyle("tcell", fontName="Helvetica", fontSize=8.4,
                            leading=10.8, textColor=DARK),
    "tcellb": ParagraphStyle("tcellb", fontName="Helvetica-Bold", fontSize=8.4,
                             leading=10.8, textColor=DARK),
    "thead": ParagraphStyle("thead", fontName="Helvetica-Bold", fontSize=8.6,
                            leading=11, textColor=white),
}


def bullet(text):
    return Paragraph(text, styles["bullet"], bulletText="•")


story = []

# ---------------------------------------------------------------- page 1
story.append(Paragraph("EPM Wizard", styles["title"]))
story.append(Paragraph(
    "A local-first, ChatGPT-style AI workspace for Oracle Enterprise Performance "
    "Management (EPM) implementation — with a fully IBM Cloud hosted deployment path.",
    styles["subtitle"]))
story.append(HRFlowable(width="100%", thickness=1.4, color=BLUE, spaceAfter=6))

story.append(Paragraph("What it is", styles["h2"]))
story.append(Paragraph(
    "EPM Wizard lets an implementation consultant build, validate, and deploy Oracle EPM "
    "artifacts — data-entry forms, business rules, cube analysis — through a conversational "
    "chat interface instead of hand-editing XML or clicking through Oracle's admin screens. "
    "It runs entirely on your machine with <b>docker compose up</b>: no hosted server, no "
    "external database, no account. It boots in Demo Mode with a deterministic local AI and a "
    "fixture Planning application, so the whole product works with zero configuration and no "
    "API key. The UI follows the IBM Carbon Design System with IBM Plex typography.",
    styles["body"]))

story.append(Paragraph("What it does", styles["h2"]))
for b in [
    "<b>Conversational form &amp; rule building</b> — \"Create an Actuals form with level-zero "
    "descendants of Total Payroll in rows\", then iterate: \"move Entity to POV\", \"hide March\", "
    "\"use aliases\", and finally \"deploy\".",
    "<b>Validation &amp; preview</b> — every specification is checked against real tenant metadata "
    "(cubes, dimensions, member existence, sizing) and rendered as an interactive EPM-style grid "
    "in the chat before anything is deployed.",
    "<b>Guarded deployment</b> — explicit approval cards, production safeguards (a persistent PROD "
    "badge plus a typed confirmation phrase), full audit records, and post-deployment verification: "
    "a form is only marked \"verified\" once Oracle confirms it exists.",
    "<b>Cube Architecture visualizer</b> — deterministic cube maps, form coverage, cell "
    "intersections, cross-cube comparison, and sizing, derived only from real metadata.",
    "<b>Context engine</b> — captures tenant metadata locally with per-section honesty "
    "(complete / partial / derived / unavailable) and shares it as portable, secret-free "
    ".epwcontext packages.",
    "<b>Complete local history</b> — projects, conversations, artifacts, deployments, and audit "
    "records persist in local SQLite and survive restarts; export/import for backup or team sharing.",
]:
    story.append(bullet(b))

story.append(Paragraph("The core design principle: deterministic artifacts", styles["h2"]))
story.append(Paragraph(
    "EPM Wizard is more than a chatbot wrapper because the language model <b>never owns the "
    "deployable artifact</b>. The model interprets intent and proposes a structured, typed "
    "specification; deterministic application code does everything that must be correct and "
    "reproducible — validation, exact member resolution (no fuzzy substitution), safe XML "
    "rendering, byte-identical packaging with SHA-256 checksums, deployment, and verification. "
    "There is no shell execution of model output: every action maps to a typed, allowlisted "
    "backend function behind a single connector boundary.",
    styles["body"]))
story.append(Paragraph(
    "Intent → context retrieval → proposed spec → Pydantic validation → tenant metadata validation "
    "→ preview → user approval → deterministic generation → deploy → verify → history",
    styles["mono"]))

story.append(Paragraph("Security posture", styles["h2"]))
for b in [
    "Secrets never reach the model, logs, chat history, context packages, or git — a centralized "
    "redactor scrubs every log line, tool result, and diagnostics bundle.",
    "API keys and passwords live in a local encrypted secret store (Fernet), not the database; "
    "pasted credentials are detected, redacted before storage, and flagged to the user.",
    "The EPM Automate runner enforces a strict command allowlist and subprocess argument arrays — "
    "never <b>shell=True</b> — with timeouts, output redaction, and no path traversal.",
]:
    story.append(bullet(b))

story.append(PageBreak())

# ---------------------------------------------------------------- page 2
story.append(Paragraph("Technical: system architecture", styles["h2"]))
story.append(Paragraph(
    "A hybrid, local-first system orchestrated by Docker Compose: a React + TypeScript SPA "
    "(Vite, IBM Carbon, TanStack Query, Zustand) talking to a FastAPI backend over HTTPS with "
    "Server-Sent Events for streaming chat. Python + Pydantic own the canonical schemas; "
    "TypeScript interfaces and Zod validators are code-generated from them, and a CI drift test "
    "fails if they diverge. Chat responses stream as typed blocks (form previews, validation "
    "reports, deployment progress, cube maps) that the client upserts in place by stable id.",
    styles["body"]))

drawing = svg2rlg(os.path.join(HERE, "arch.svg"))
avail_w = PAGE_W - 2 * MARGIN
scale = min(1.0, avail_w / drawing.width)
drawing.width *= scale
drawing.height *= scale
drawing.scale(scale, scale)
story.append(drawing)
story.append(Paragraph(
    "The connector boundary is the single authoritative EPM integration point — the model can "
    "never call Oracle REST or EPM Automate directly, and operations are classified "
    "read-only / execution / modifying / destructive, with the latter two requiring explicit approval.",
    styles["caption"]))

story.append(Paragraph("IBM Cloud: the implementation and the goal", styles["h2"]))
story.append(Paragraph(
    "The goal is an <b>all-IBM hosted topology</b> for teams — \"email invite + link → sign in → "
    "request to cloud\" — while local development stays unchanged. The plan: train an AI on the "
    "team's own EPM data on IBM Cloud, run inference on watsonx.ai, host the site on Code Engine, "
    "gate access with App ID (optionally behind an IBM VPN), and plug into Oracle EPM through the "
    "existing connector boundary. A local exporter turns validated work — conversations plus "
    "Pydantic-validated form/rule artifacts — into a fully redacted instruction-tuning corpus, so "
    "the tuned Granite model learns exactly the deterministic, validated structure the product "
    "already enforces. Training has two paths: managed <b>Tuning Studio</b> (no GPUs to manage, "
    "billed per run), or <b>GPU-as-a-Service</b> VPC instances for full fine-tunes, deprovisioned "
    "after each run. Everything is provisioned by Terraform plus a deploy script in "
    "<b>deploy/ibm-cloud/</b>, and Code Engine scales to zero when idle, keeping small-team cost near zero.",
    styles["body"]))

thead = styles["thead"]; tc = styles["tcell"]; tb = styles["tcellb"]
rows = [
    [Paragraph("Need", thead), Paragraph("IBM Cloud service", thead), Paragraph("Role in EPM Wizard", thead)],
    [Paragraph("AI inference", tb), Paragraph("watsonx.ai (Granite models)", tc),
     Paragraph("First-class provider type, selectable in Settings like any other", tc)],
    [Paragraph("AI training", tb), Paragraph("Tuning Studio / GPU-as-a-Service", tc),
     Paragraph("Tune Granite on the redacted corpus exported from local usage", tc)],
    [Paragraph("Hosting", tb), Paragraph("Code Engine + Container Registry", tc),
     Paragraph("The two existing Docker images deploy unchanged; scales to zero", tc)],
    [Paragraph("Access &amp; invites", tb), Paragraph("App ID (OIDC) · optional Client-to-Site VPN", tc),
     Paragraph("Email-invite onboarding; default is browser-only — no VPN client needed", tc)],
    [Paragraph("Secrets", tb), Paragraph("Secrets Manager", tc),
     Paragraph("Oracle credentials and API keys injected as Code Engine secrets", tc)],
    [Paragraph("Storage &amp; data", tb), Paragraph("Cloud Object Storage · Databases for PostgreSQL", tc),
     Paragraph("Corpus and backups in COS; optional managed Postgres for real teams", tc)],
]
table = Table(rows, colWidths=[0.95 * inch, 2.2 * inch, avail_w - 3.15 * inch])
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), BLUE),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#f2f4f8")]),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#c6c6c6")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(table)

story.append(Spacer(1, 6))
story.append(Paragraph(
    "In hosted mode the backend reaches Oracle EPM Cloud outbound over HTTPS from the VPC — no "
    "inbound exposure — and every local safeguard (validation gates, PROD confirmation phrase, "
    "audit records, post-deployment verification) applies unchanged. The database has three tiers: "
    "ephemeral demo, single-instance SQLite with scheduled backups to COS, or managed PostgreSQL "
    "with the same Alembic migrations for teams that need to scale past one instance.",
    styles["body"]))


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
frame = Frame(MARGIN, 0.55 * inch, PAGE_W - 2 * MARGIN, PAGE_H - 1.1 * inch,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])
doc.build(story)
print("wrote", OUT)
