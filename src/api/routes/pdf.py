from datetime import datetime
from io import BytesIO
from pathlib import Path
import re

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    Image,
)

# ------------------------------------------------------------------
#  CONFIG
# ------------------------------------------------------------------

# Chemin du logo IT-STORM
# Tu peux laisser le chemin relatif si tu lances uvicorn depuis
# le dossier racine du projet. Sinon, mets ton chemin absolu ici.
LOGO_PATH = Path(__file__).resolve().parents[2] / "src" / "ui" / "assets" / "itstorm_logo.png"

# Couleurs charte IT-STORM
NAVY = colors.HexColor("#0F172A")
BLUE = colors.HexColor("#1D4ED8")
LIGHT_BLUE = colors.HexColor("#E0F2FE")
GRAY = colors.HexColor("#6B7280")
LIGHT_GRAY = colors.HexColor("#E5E7EB")

router = APIRouter(prefix="/pdf", tags=["PDF"])


class DailyPdfRequest(BaseModel):
    summary_text: str
    human_text: str | None = None
    generated_at: str | None = None


# ------------------------------------------------------------------
#  STYLES
# ------------------------------------------------------------------


def _build_styles():
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        "TitlePremium",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=NAVY,
        alignment=0,  # left
    )

    subtitle = ParagraphStyle(
        "Subtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=GRAY,
        leading=14,
        alignment=0,
    )

    section = ParagraphStyle(
        "Section",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=6,
    )

    normal = ParagraphStyle(
        "NormalText",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#111827"),
    )

    bullet = ParagraphStyle(
        "Bullet",
        parent=normal,
        leftIndent=12,
        bulletIndent=0,
    )

    code = ParagraphStyle(
        "Code",
        parent=base["Code"],
        fontName="Courier",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4B5563"),
    )

    small = ParagraphStyle(
        "Small",
        parent=normal,
        fontSize=8,
        textColor=GRAY,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "section": section,
        "normal": normal,
        "bullet": bullet,
        "code": code,
        "small": small,
    }


# ------------------------------------------------------------------
#  HELPERS MARKDOWN → TEXTE / TABLE
# ------------------------------------------------------------------


def _clean_md_inline(text: str) -> str:
    """
    Transforme un peu de Markdown en texte/HTML compatible Paragraph :
    - **gras** → <b>gras</b>
    - _italique_ ou *italique* → <i>italique</i>
    """
    if not text:
        return ""

    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italique *text* ou _text_
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)

    return text


def _parse_summary_blocks(summary_text: str):
    """
    Découpe summary_text en blocs logiques :
    - intro
    - tech
    - market
    - mlops
    - footer
    """
    blocks = {
        "intro": [],
        "tech": [],
        "market": [],
        "mlops": [],
        "footer": [],
    }

    current = "intro"
    for raw in summary_text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        # On ignore le gros titre Markdown "# 📊 StormCopilot – Rapport quotidien"
        if stripped.startswith("# "):
            continue

        if stripped.startswith("## 📡 Tech Radar"):
            current = "tech"
            continue
        if stripped.startswith("## 📈 Market Radar"):
            current = "market"
            continue
        if stripped.startswith("## 🧠 MLOps"):
            current = "mlops"
            continue
        if stripped.startswith("---"):
            current = "footer"
            continue

        blocks[current].append(line)

    return blocks


def _extract_table_block(lines: list[str], start_idx: int):
    """
    À partir d'un index dans 'lines', si on a une table Markdown:
    | col1 | col2 |
    | ---  | ---  |
    | ...  | ...  |
    on renvoie (rows, next_index)
    """
    table_lines = []
    i = start_idx

    while i < len(lines):
        l = lines[i].strip()
        if not l.startswith("|") or "|" not in l[1:]:
            break
        table_lines.append(l)
        i += 1

    if len(table_lines) < 2:
        return None, start_idx

    # On ignore la ligne de séparation --- si présente (2e ligne)
    rows = []
    for idx, l in enumerate(table_lines):
        # split par '|' et strip
        parts = [c.strip() for c in l.split("|")[1:-1]]
        # si ligne de séparateurs, on saute
        if idx == 1 and all(set(p) <= {"-", ":", " "} and p for p in parts):
            continue
        rows.append(parts)

    if not rows:
        return None, start_idx

    return rows, i


def _build_table_flowable(rows, styles):
    """
    Construit une vraie Table ReportLab avec charte IT-STORM.
    """
    table = Table(rows, hAlign="LEFT")

    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
    )
    table.setStyle(style)
    return table


def _add_block_as_paragraphs(story, styles, title: str, lines: list[str]):
    if not lines:
        return

    story.append(Paragraph(title, styles["section"]))

    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.strip()
        if not line:
            i += 1
            continue

        # TABLE MARKDOWN ?
        if line.startswith("|") and "|" in line[1:]:
            rows, next_i = _extract_table_block(lines, i)
            if rows:
                story.append(_build_table_flowable(rows, styles))
                story.append(Spacer(1, 0.2 * cm))
                i = next_i
                continue

        # Citation "> ..."
        if line.startswith(">"):
            txt = _clean_md_inline(line[1:].strip())
            story.append(Paragraph(txt, styles["normal"]))
            i += 1
            continue

        # Texte normal
        txt = _clean_md_inline(line)
        story.append(Paragraph(txt, styles["normal"]))
        i += 1

    story.append(Spacer(1, 0.3 * cm))


# ------------------------------------------------------------------
#  HEADER / RÉSUMÉ
# ------------------------------------------------------------------


def _add_header(story, styles, ts_iso: str | None):
    ts = ts_iso or datetime.utcnow().isoformat()
    date_str = ts.replace("T", " ")[:19]

    # Bandeau logo + titre
    elements = []

    # Logo si dispo
    if LOGO_PATH.exists():
        try:
            img = Image(str(LOGO_PATH))
            img._restrictSize(2.8 * cm, 2.8 * cm)
            elements.append(img)
        except Exception:
            img = None

    # Titre + sous-titre dans une "colonne"
    title_para = [
        Paragraph("StormCopilot – Rapport quotidien", styles["title"]),
        Paragraph(
            "Synthèse automatique Tech Radar · Market Radar · MLOps",
            styles["subtitle"],
        ),
    ]

    if elements:
        # Table à deux colonnes : logo | titre
        t = Table(
            [[elements[0], title_para]],
            colWidths=[3 * cm, 14 * cm],
            hAlign="LEFT",
        )
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(t)
    else:
        # Sans logo, on garde le titre classique
        story.append(Paragraph("StormCopilot – Rapport quotidien", styles["title"]))
        story.append(
            Paragraph(
                "Synthèse automatique Tech Radar · Market Radar · MLOps",
                styles["subtitle"],
            )
        )

    story.append(Spacer(1, 0.4 * cm))

    # Ligne date
    story.append(
        Paragraph(
            f"Généré le : <b>{date_str}</b>",
            styles["normal"],
        )
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=LIGHT_GRAY,
            lineCap="round",
        )
    )
    story.append(Spacer(1, 0.4 * cm))


def _add_executive_summary(story, styles, human_text: str | None):
    if not human_text:
        return

    story.append(Paragraph("Résumé exécutif", styles["section"]))
    lines = (human_text or "").split("\n")

    for line in lines:
        l = line.strip()
        if not l:
            continue
        if l.startswith("- "):
            txt = _clean_md_inline(l[2:].strip())
            story.append(Paragraph(f"• {txt}", styles["bullet"]))
        else:
            txt = _clean_md_inline(l)
            story.append(Paragraph(txt, styles["normal"]))
    story.append(Spacer(1, 0.4 * cm))


# ------------------------------------------------------------------
#  ROUTE PRINCIPALE
# ------------------------------------------------------------------


@router.post("/daily-report")
def generate_daily_report(payload: DailyPdfRequest):
    """
    Génère un PDF premium à partir de :
    - summary_text : markdown détaillé (tech, market, mlops)
    - human_text   : résumé exécutif lisible
    - generated_at : timestamp ISO
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    styles = _build_styles()
    story = []

    # Header
    _add_header(story, styles, payload.generated_at)

    # Résumé exécutif
    _add_executive_summary(story, styles, payload.human_text)

    # Corps détaillé (on découpe le markdown)
    blocks = _parse_summary_blocks(payload.summary_text)

    _add_block_as_paragraphs(story, styles, "Introduction", blocks["intro"])
    _add_block_as_paragraphs(
        story,
        styles,
        "Tech Radar – Veille technologique",
        blocks["tech"],
    )
    _add_block_as_paragraphs(
        story,
        styles,
        "Market Radar – Analyse des actifs",
        blocks["market"],
    )
    _add_block_as_paragraphs(
        story,
        styles,
        "MLOps – Champions & Monitoring",
        blocks["mlops"],
    )

    # Footer
    if blocks["footer"]:
        story.append(Spacer(1, 0.2 * cm))
        story.append(
            HRFlowable(
                width="40%",
                thickness=0.8,
                color=LIGHT_GRAY,
                lineCap="round",
                spaceBefore=6,
                spaceAfter=6,
            )
        )
        for line in blocks["footer"]:
            l = line.strip()
            if not l:
                continue
            txt = _clean_md_inline(l)
            story.append(Paragraph(txt, styles["small"]))

    # Signature StormCopilot
    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            "StormCopilot – IT-STORM Consulting · Rapport généré automatiquement.",
            styles["small"],
        )
    )

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = "stormcopilot_daily_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
