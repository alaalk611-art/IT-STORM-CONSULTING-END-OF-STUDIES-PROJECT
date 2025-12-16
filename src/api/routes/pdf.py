from __future__ import annotations

from datetime import datetime
from io import BytesIO
import os
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.platypus import ListFlowable, ListItem
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
    PageBreak,
    KeepTogether,
)

router = APIRouter(prefix="/pdf", tags=["PDF"])


# --------------------------------------------------------------------
# 📌 Model n8n → FastAPI (STRUCTURÉ = rendu premium)
# --------------------------------------------------------------------
class DailyPdfRequest(BaseModel):
    # Conservés (tu les envoies déjà)
    summary_text: str | None = None  # gardé si tu veux, mais on ne l’affiche plus
    human_text: str | None = None
    generated_at: str | None = None

    tech_radar: dict | None = None
    market_ai_summary: dict | None = None
    market_ai_rows: list[dict] | None = None
    market_radar_assets: list[dict] | None = None
    mlops_summary: dict | None = None

    # ✅ AJOUT (pour rendu complet MLOps)
    mlops_kpis: dict | None = None
    mlops_decision: dict | None = None
    mlops_champions_rows: list[dict] | None = None

    ohlcv_by_symbol: dict[str, list[dict]] | None = None

    # ✅ AJOUT (Traçabilité + Quality Gate)
    trace: dict | None = None
    quality_ok: bool | None = None
    quality_level: str | None = None
    quality_reason: str | None = None



# --------------------------------------------------------------------
# 🎨 Helpers : dates / emojis / nettoyages
# --------------------------------------------------------------------
def _pretty_dt(ts_iso: str | None) -> str:
    if not ts_iso:
        ts_iso = datetime.utcnow().isoformat()
    ts_iso = ts_iso.replace("Z", "")
    return ts_iso.replace("T", " ")[:19]


def _safe(txt: Any) -> str:
    return (str(txt) if txt is not None else "").strip()


def _strip_md_artifacts(line: str) -> str:
    s = (line or "").strip()
    s = re.sub(r"^\s*#+\s*", "", s)
    s = s.replace("**", "")
    return s


def _fmt_num(x: Any, digits: int = 2) -> str:
    try:
        if x is None or x == "":
            return "-"
        v = float(x)
        return f"{v:.{digits}f}"
    except Exception:
        return _safe(x) or "-"


def _fmt_pct(x: Any, digits: int = 1) -> str:
    try:
        if x is None or x == "":
            return "-"
        v = float(x)
        return f"{v:.{digits}f}%"
    except Exception:
        return _safe(x) or "-"


def _badge_for_signal(sig: str) -> tuple[str, colors.Color]:
    s = (sig or "").upper().strip()
    if s == "ACHAT":
        return "🟢 ACHAT", colors.HexColor("#16A34A")
    if s == "VENTE":
        return "🔴 VENTE", colors.HexColor("#DC2626")
    return "⚪ NEUTRE", colors.HexColor("#64748B")


def _quality_badge(q: str | None) -> tuple[str, colors.Color]:
    t = (q or "").lower()
    if "✅" in (q or "") or "complet" in t or "ok" in t:
        return "✅ Complet", colors.HexColor("#16A34A")
    if "⚠" in (q or "") or "incomplet" in t or "partial" in t or "vide" in t:
        return "⚠ Incomplet", colors.HexColor("#F59E0B")
    if "❌" in (q or "") or "error" in t or "échec" in t:
        return "❌ Erreur", colors.HexColor("#DC2626")
    return "⚠ Incomplet", colors.HexColor("#F59E0B")


def _emoji_warning(warning: str | None) -> str:
    w = (warning or "").strip().upper()
    if not w or w in ("NONE", "NULL"):
        return "🟢"
    if w in ("NO_DATA", "TIMEOUT", "ERROR", "KO"):
        return "🔴"
    return "🟠"


# --------------------------------------------------------------------
# 🎨 Styles premium IT-STORM
# --------------------------------------------------------------------
def _build_styles():
    base = getSampleStyleSheet()

    blue_dark = "#0B1220"   # navy
    blue_sky = "#38BDF8"    # sky
    slate = "#1E293B"
    text = "#0F172A"

    title = ParagraphStyle(
        "TitlePremium",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=26,
        textColor=colors.HexColor(text),
        alignment=1,
    )

    subtitle = ParagraphStyle(
        "Subtitle",
        parent=base["Normal"],
        fontSize=10.5,
        textColor=colors.HexColor(slate),
        leading=14,
        alignment=1,
    )

    cover_title = ParagraphStyle(
        "CoverTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        textColor=colors.HexColor(text),
        alignment=1,
    )

    cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=base["Normal"],
        fontSize=12,
        textColor=colors.HexColor(slate),
        leading=16,
        alignment=1,
    )

    section = ParagraphStyle(
        "Section",
        parent=base["Heading2"],
        fontSize=14.5,
        textColor=colors.HexColor(blue_sky),
        leading=18,
        spaceBefore=12,
        spaceAfter=6,
    )

    h3 = ParagraphStyle(
        "H3",
        parent=base["Heading3"],
        fontSize=11.5,
        textColor=colors.HexColor(text),
        leading=14,
        spaceBefore=7,
        spaceAfter=4,
    )

    normal = ParagraphStyle(
        "NormalText",
        parent=base["Normal"],
        fontSize=10.2,
        leading=14,
        textColor=colors.HexColor("#111827"),
    )

    small = ParagraphStyle(
        "Small",
        parent=normal,
        fontSize=8.7,
        textColor=colors.HexColor("#6B7280"),
    )

    pill = ParagraphStyle(
        "Pill",
        parent=base["Normal"],
        fontSize=9.5,
        leading=12,
        textColor=colors.white,
        alignment=1,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "cover_title": cover_title,
        "cover_subtitle": cover_subtitle,
        "section": section,
        "h3": h3,
        "normal": normal,
        "small": small,
        "pill": pill,
        "blue_dark": blue_dark,
        "blue_sky": blue_sky,
        "slate": slate,
        "text": text,
    }


# --------------------------------------------------------------------
# 🖼️ Logo helper
# --------------------------------------------------------------------
def _get_logo_path() -> str:
    logo_path = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\src\ui\assets\itstorm_logo.png"
    if os.path.exists(logo_path):
        return logo_path

    rel = os.path.join(os.getcwd(), "src", "ui", "assets", "itstorm_logo.png")
    if os.path.exists(rel):
        return rel

    return ""


# --------------------------------------------------------------------
# ✅ UI blocks (Power BI-like)
# --------------------------------------------------------------------
def _kpi_card(title: str, value: str, subtitle: str, accent_hex: str, width_cm: float = 5.2) -> Table:
    data = [
        [Paragraph(f"<b>{_safe(title)}</b>", ParagraphStyle("k1", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white))],
        [Paragraph(f"<b>{_safe(value)}</b>", ParagraphStyle("k2", fontName="Helvetica-Bold", fontSize=18, textColor=colors.white))],
        [Paragraph(_safe(subtitle), ParagraphStyle("k3", fontName="Helvetica", fontSize=8.5, textColor=colors.white))],
    ]
    tbl = Table(data, colWidths=[width_cm * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(accent_hex)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#0B1220")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, colors.HexColor("#38BDF8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _badge(text: str, bg: colors.Color) -> Table:
    p = Paragraph(f"<b>{_safe(text)}</b>", ParagraphStyle("bdg", fontName="Helvetica-Bold", fontSize=9.2, textColor=colors.white, alignment=1))
    t = Table([[p]], colWidths=[5.8 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#0B1220")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _style_table_default(table: Table):
    """Style 'dashboard' : bordure externe plus marquée + grille interne légère."""
    table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1220")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.6),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),

        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 9.2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),

        # Borders / grid
        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#0B1220")),     # bordure externe (plus premium)
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),  # grille interne légère
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, colors.HexColor("#38BDF8")),    # ligne accent sous header

        # Padding
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))


# --------------------------------------------------------------------
# 📌 Page de garde (Cover)
# --------------------------------------------------------------------
def _add_cover_page(story, styles, ts_iso: str | None):
    date_str = _pretty_dt(ts_iso)

    story.append(Spacer(1, 1.2 * cm))

    logo_path = _get_logo_path()
    if logo_path:
        img = Image(logo_path, width=5.0 * cm, height=5.0 * cm)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.8 * cm))
    else:
        story.append(Spacer(1, 1.2 * cm))

    story.append(Paragraph("StormCopilot", styles["cover_title"]))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph("Rapport quotidien", styles["cover_subtitle"]))
    story.append(Spacer(1, 0.6 * cm))

    band = Table(
        [[
            Paragraph("📡 Tech Radar", styles["pill"]),
            Paragraph("📈 Market Radar", styles["pill"]),
            Paragraph("🧠 MLOps", styles["pill"]),
        ]],
        colWidths=[5.2 * cm, 5.2 * cm, 5.2 * cm],
    )
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(styles["blue_dark"])),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor(styles["blue_sky"])),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#1E293B")),
    ]))
    story.append(band)

    story.append(Spacer(1, 0.7 * cm))
    story.append(Paragraph(f"Généré le : <b>{date_str}</b>", styles["normal"]))
    story.append(Spacer(1, 0.4 * cm))

    story.append(HRFlowable(width="80%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.6 * cm))

    story.append(
        Paragraph(
            "Rapport généré automatiquement via n8n + FastAPI + MLflow.<br/>"
            "Rendu premium type “dashboard entreprise”.",
            styles["subtitle"],
        )
    )

    story.append(Spacer(1, 6.0 * cm))
    story.append(Paragraph("IT-STORM Consulting · StormCopilot", styles["small"]))
    story.append(PageBreak())


# --------------------------------------------------------------------
# 📌 Header (pages internes)
# --------------------------------------------------------------------
def _add_header(story, styles, ts_iso: str | None):
    date_str = _pretty_dt(ts_iso)

    logo_path = _get_logo_path()
    if logo_path:
        img = Image(logo_path, width=2.6 * cm, height=2.6 * cm)
        img.hAlign = "LEFT"
        story.append(img)

    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph("StormCopilot – Rapport quotidien", styles["title"]))
    story.append(Paragraph("Synthèse automatique Tech Radar · Market Radar · MLOps", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f"Généré le : <b>{date_str}</b>", styles["normal"]))
    story.append(Spacer(1, 0.2 * cm))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.4 * cm))


# --------------------------------------------------------------------
# ✅ Dashboard premium (KPIs + badges)
# --------------------------------------------------------------------
def _add_dashboard_page(story, styles, payload: DailyPdfRequest):
    story.append(Paragraph("Dashboard exécutif", styles["section"]))
    story.append(Paragraph("Vue KPI rapide (style Power BI)", styles["normal"]))
    story.append(Spacer(1, 0.25 * cm))

    tr = payload.tech_radar or {}
    tm = (tr.get("metrics") or {}) if isinstance(tr, dict) else {}
    tq_txt, tq_col = _quality_badge(_safe(tr.get("quality")))

    sources_ok = tm.get("sources_ok", tm.get("nb_ok", 0))
    sources_total = tm.get("sources_total", tm.get("nb_total", 0))
    tech_sources = f"{sources_ok}/{sources_total}"
    tech_hot = str(tm.get("hot", 0))
    tech_trending = str(tm.get("trending", 0))

    ms = payload.market_ai_summary or {}
    nb_assets = ms.get("nb_assets", 0)
    achat = ms.get("achat", 0)
    neutre = ms.get("neutre", 0)
    mean_trend = ms.get("tendance_moyenne_pct", None)
    mean_vol = ms.get("volatilite_moyenne_pct", None)

    row1 = Table([[
        _kpi_card("📡 Tech Sources", str(tech_sources), "Sources actives", styles["blue_dark"]),
        _kpi_card("🔥 Hot", tech_hot, "Articles “hot”", "#111827"),
        _kpi_card("⭐ Trending", tech_trending, "Tendance 24–48h", "#0F172A"),
    ]], colWidths=[5.3*cm, 5.3*cm, 5.3*cm])
    row1.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(row1)
    story.append(Spacer(1, 0.25 * cm))

    row2 = Table([[
        _kpi_card("📈 Actifs", str(nb_assets), "Analysés (Market)", styles["blue_dark"]),
        _kpi_card("🟢 ACHAT", str(achat), "Signaux achat", "#065F46"),
        _kpi_card("⚪ NEUTRE", str(neutre), "Signaux neutres", "#334155"),
    ]], colWidths=[5.3*cm, 5.3*cm, 5.3*cm])
    row2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(row2)

    story.append(Spacer(1, 0.25 * cm))
    story.append(KeepTogether([
        _badge(f"Qualité Tech Radar : {tq_txt}", tq_col),
        Spacer(1, 0.12 * cm),
        Paragraph(
            f"🧭 Tendance moyenne : <b>{_fmt_pct(mean_trend, 1)}</b>  ·  🌪 Volatilité moyenne : <b>{_fmt_pct(mean_vol, 1)}</b>",
            styles["normal"],
        ),
    ]))

    headline = _safe(tr.get("headline"))
    if headline:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(f"🗞 Headline : {headline}", styles["small"]))

    mtxt = _safe(ms.get("text"))
    if mtxt:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(f"💬 {mtxt}", styles["normal"]))

    story.append(Spacer(1, 0.35 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.2 * cm))


# --------------------------------------------------------------------
# ✅ Résumé exécutif (lisible)
# --------------------------------------------------------------------
def _add_executive_summary(story, styles, human_text: str | None):
    if not human_text:
        return

    story.append(Paragraph("Résumé exécutif", styles["section"]))
    for line in human_text.split("\n"):
        line = _strip_md_artifacts(line).strip()
        if not line:
            continue
        if line.startswith("-"):
            story.append(Paragraph(f"• {line[1:].strip()}", styles["normal"]))
        else:
            story.append(Paragraph(line, styles["normal"]))
    story.append(Spacer(1, 0.35 * cm))


# --------------------------------------------------------------------
# ✅ Tech Radar (STRUCTURÉ)
# --------------------------------------------------------------------
def _add_tech_section(story, styles, tech_radar: dict | None):
    story.append(Paragraph("📡 Tech Radar", styles["section"]))

    tr = tech_radar or {}
    tm = (tr.get("metrics") or {}) if isinstance(tr, dict) else {}

    q_txt, q_col = _quality_badge(_safe(tr.get("quality")))
    story.append(_badge(f"Qualité : {q_txt}", q_col))
    story.append(Spacer(1, 0.15 * cm))

    sources_ok = tm.get("sources_ok", tm.get("nb_ok", 0))
    sources_total = tm.get("sources_total", tm.get("nb_total", 0))
    hot = tm.get("hot", 0)
    trending = tm.get("trending", 0)
    fresh = tm.get("fresh", 0)

    data = [
        ["Indicateur", "Valeur"],
        ["Sources actives", f"{sources_ok} / {sources_total}"],
        ["🔥 Hot", str(hot)],
        ["⭐ Trending", str(trending)],
        ["🆕 Fresh", str(fresh)],
        ["Statut", _safe(tr.get("status")) or "-"],
    ]
    tbl = Table(data, colWidths=[6.2*cm, 9.4*cm])
    _style_table_default(tbl)
    story.append(tbl)

    headline = _safe(tr.get("headline"))
    if headline:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(f"🗞 <b>Headline</b> : {headline}", styles["normal"]))

    story.append(Spacer(1, 0.35 * cm))


# --------------------------------------------------------------------
# ✅ Market IA (STRUCTURÉ + coloration)
# --------------------------------------------------------------------
def _add_market_ai_table(story, styles, rows: list[dict] | None, market_ai_summary: dict | None):
    story.append(Paragraph("📈 Market Radar (IA)", styles["section"]))

    ms = market_ai_summary or {}
    if ms:
        mini = Table([
            ["KPI", "Valeur"],
            ["Actifs analysés", str(ms.get("nb_assets", "-"))],
            ["🟢 ACHAT", str(ms.get("achat", "-"))],
            ["🔴 VENTE", str(ms.get("vente", "-"))],
            ["⚪ NEUTRE", str(ms.get("neutre", "-"))],
            ["🧭 Tendance moyenne", _fmt_pct(ms.get("tendance_moyenne_pct"), 1)],
            ["🌪 Volatilité moyenne", _fmt_pct(ms.get("volatilite_moyenne_pct"), 1)],
        ], colWidths=[6.2 * cm, 9.4 * cm])
        _style_table_default(mini)
        story.append(mini)

        txt = _safe(ms.get("text"))
        if txt:
            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph(f"💬 {txt}", styles["normal"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("📄 Détail IA par symbole", styles["h3"]))

    if not rows:
        story.append(Paragraph("Aucune ligne IA.", styles["normal"]))
        story.append(Spacer(1, 0.25 * cm))
        return

    # --- TABLE PRINCIPALE (SANS LECTURE) ---
    header = ["Symbole", "Prix", "Signal", "Score", "Tendance (ann.)", "Vol 20j (ann.)", "RSI14"]
    data = [header]

    # On stocke Lecture à part
    lectures = []  # list[tuple(symbole, lecture_str)]
    for r in rows:
        sym = _safe(r.get("symbol"))
        prix = _fmt_num(r.get("prix"), 3)

        sig_raw = _safe(r.get("signal")).upper()
        sig_txt, _ = _badge_for_signal(sig_raw)

        score = _fmt_num(r.get("score"), 2)

        trend = r.get("tendance_annuelle_pct", r.get("tendance_annuelle_%"))
        vol = r.get("vol20_annuelle_pct", r.get("vol20_annuelle_%"))
        rsi = r.get("rsi14", r.get("RSI14"))

        lec = _safe(r.get("lecture")).strip()
        if lec:
            lectures.append((sym, lec))

        data.append([
            sym,
            prix,
            sig_txt,
            score,
            _fmt_pct(trend, 1),
            _fmt_pct(vol, 1),
            _fmt_num(rsi, 1),
        ])

    col_widths = [2.0 * cm, 2.1 * cm, 2.6 * cm, 1.6 * cm, 2.7 * cm, 2.7 * cm, 1.6 * cm]
    tbl = Table(data, colWidths=col_widths)
    _style_table_default(tbl)

    tbl.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "CENTER"),   # symbole
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),    # prix
        ("ALIGN", (2, 1), (2, -1), "CENTER"),   # signal
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),    # score
        ("ALIGN", (4, 1), (6, -1), "RIGHT"),    # % + RSI
    ]))

    green = colors.HexColor("#16A34A")
    red = colors.HexColor("#DC2626")
    amber = colors.HexColor("#F59E0B")

    for i in range(1, len(data)):
        tbl.setStyle(TableStyle([("TEXTCOLOR", (3, i), (3, i), amber)]))  # score
        try:
            tv = float(str(data[i][4]).replace("%", "").strip())
            tbl.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), green if tv >= 0 else red)]))
        except Exception:
            pass

    story.append(tbl)

    # --- LECTURE EN DESSOUS (LISTE PREMIUM, PLUS ORGANISÉE) ---
    if lectures:
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("🧾 Lecture par symbole", styles["h3"]))
        story.append(Spacer(1, 0.10 * cm))

        def _normalize_lecture(lec: str) -> str:
            """
            Transforme: 'NEUTRE • haussière • vol normale'
            en:         'NEUTRE • tendance haussière • volatilité normale'
            (si déjà ok, on garde)
            """
            s = (lec or "").strip()
            if not s:
                return ""

            parts = [p.strip() for p in s.split("•") if p.strip()]
            if not parts:
                return s

            # 0) signal
            sig = parts[0]
            parts[0] = sig

            # 1) tendance
            if len(parts) >= 2:
                t = parts[1]
                if not t.lower().startswith("tendance"):
                    t = f"tendance {t}"
                parts[1] = t

            # 2) volatilité
            if len(parts) >= 3:
                v = parts[2]
                v_low = v.lower()

                if v_low.startswith("vol "):
                    v = "volatilité " + v[4:].strip()
                elif v_low.startswith("vol"):
                    if not v_low.startswith("volatilité"):
                        v = v.replace("vol", "volatilité", 1).strip()
                elif not v_low.startswith("volatilité"):
                    v = f"volatilité {v}"

                parts[2] = v

            return " • ".join(parts)

        bullet_items = []
        for sym, lec in lectures:
            nice = _normalize_lecture(lec)

            # rendu "pro" : symbole en gras + lecture sur ligne suivante
            p = Paragraph(
                f"<b>{_safe(sym)}</b><br/><font size='9'><b>{nice}</b></font>",
                styles["normal"]
            )
            bullet_items.append(ListItem(p, leftIndent=16, spaceBefore=3, spaceAfter=3))

        story.append(ListFlowable(
            bullet_items,
            bulletType="bullet",
            bulletFontName="Helvetica",
            bulletFontSize=9,
            leftIndent=14,
            bulletDedent=6,
        ))

    story.append(Spacer(1, 0.35 * cm))

# --------------------------------------------------------------------
# ✅ Market assets (STRUCTURÉ)
# --------------------------------------------------------------------
def _add_market_assets_table(story, styles, assets: list[dict] | None):
    if not assets:
        return

    story.append(Paragraph("🧾 Données marché (assets)", styles["h3"]))

    header = ["Symbole", "Bougies", "Source", "Intervalle", "Période", "Statut"]
    data = [header]
    for a in assets:
        data.append([
            _safe(a.get("symbol")),
            _safe(a.get("nb_candles", "-")),
            _safe(a.get("source", "-")),
            _safe(a.get("interval", "-")),
            _safe(a.get("period", "-")),
            _emoji_warning(_safe(a.get("warning"))),
        ])

    tbl = Table(data, colWidths=[2.4*cm, 2.0*cm, 3.0*cm, 2.1*cm, 2.1*cm, 1.9*cm])
    _style_table_default(tbl)
    story.append(tbl)
    story.append(Spacer(1, 0.35 * cm))



# --------------------------------------------------------------------
# ✅ MLOps (STRUCTURÉ)
# --------------------------------------------------------------------
def _add_mlops_section(story, styles, payload: DailyPdfRequest):
    story.append(Paragraph("🧠 MLOps", styles["section"]))

    ms = payload.mlops_summary or {}
    k = payload.mlops_kpis or {}
    d = payload.mlops_decision or {}
    rows = payload.mlops_champions_rows or []

    # fallback : si n8n envoie raw_champions dans mlops_summary
    if not rows:
        rc = ms.get("raw_champions") if isinstance(ms, dict) else None
        if isinstance(rc, dict):
            built = []
            for sym, obj in rc.items():
                if not isinstance(obj, dict):
                    continue
                met = obj.get("metrics") or {}
                built.append({
                    "symbol": sym,
                    "silhouette": met.get("silhouette"),
                    "ae_reconstruction": met.get("ae_reconstruction"),
                    "score": obj.get("score"),
                    "run_id": obj.get("run_id"),
                })
            rows = built

    # --- KPIs principaux ---
    pipeline_status = _safe(ms.get("pipeline_status") or k.get("pipeline_status") or "")
    nb_ok = ms.get("nb_symbols_ok", k.get("nb_symbols_ok", "-"))
    nb_req = ms.get("nb_symbols_requested", k.get("nb_symbols_requested", "-"))
    nb_champ = ms.get("nb_champions", k.get("nb_champions", "-"))
    drift_avg = ms.get("drift_avg", d.get("drift_avg", None))
    drift_max = ms.get("drift_max", d.get("drift_max", None))

    retrain = d.get("retrain_recommended", ms.get("retrain_recommended", False))
    retrain_txt = "✅ Non" if retrain is False else "⚠ Oui"

    row1 = Table([[
        _kpi_card("✅ Pipeline", pipeline_status or "OK", "Statut MLOps", "#16A34A" if (pipeline_status or "OK").strip().upper() in ("OK","SUCCESS","DONE") else "#F59E0B"),
        _kpi_card("🎯 Symboles OK", str(nb_ok), f"Demandés : {nb_req}", "#111827"),
        _kpi_card("🏆 Champions", str(nb_champ), "Nb champions", "#0F172A"),
    ]], colWidths=[5.3*cm, 5.3*cm, 5.3*cm])
    row1.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(row1)
    story.append(Spacer(1, 0.25 * cm))

    row2 = Table([[
        _kpi_card("📉 Drift moyen", _fmt_num(drift_avg, 3), "Qualité data", styles["blue_dark"]),
        _kpi_card("📈 Drift max", _fmt_num(drift_max, 3), "Pic observé", "#111827"),
        _kpi_card("🔁 Retrain", retrain_txt, "Recommandation", "#334155"),
    ]], colWidths=[5.3*cm, 5.3*cm, 5.3*cm])
    row2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(row2)

    explanation = _safe(d.get("explanation") or ms.get("decision_explanation"))
    if explanation:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(f"💬 {explanation}", styles["normal"]))

    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("🏆 Détail des champions", styles["h3"]))

    if not rows:
        story.append(Paragraph("Aucune donnée champions fournie.", styles["normal"]))
        story.append(Spacer(1, 0.35 * cm))
        return

    header = ["Symbol", "Silhouette", "Reconstruction AE", "Score global", "run_id"]
    data = [header]

    # tri : score meilleur en haut (moins négatif)
    try:
        rows = sorted(rows, key=lambda r: float(r.get("score", -999)), reverse=True)
    except Exception:
        pass

    for r in rows:
        data.append([
            _safe(r.get("symbol")),
            _fmt_num(r.get("silhouette"), 3),
            _fmt_num(r.get("ae_reconstruction"), 3),
            _fmt_num(r.get("score"), 3),
            _safe(r.get("run_id")) or "-",
        ])

    tbl = Table(data, colWidths=[2.0*cm, 2.4*cm, 3.4*cm, 2.4*cm, 5.9*cm])
    _style_table_default(tbl)

    # coloration score
    amber = colors.HexColor("#F59E0B")
    tbl.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (1, 1), (3, -1), "RIGHT"),
        ("TEXTCOLOR", (3, 1), (3, -1), amber),
    ]))

    story.append(tbl)
    story.append(Spacer(1, 0.35 * cm))


# --------------------------------------------------------------------
# ✅ OHLCV (optionnel)
# --------------------------------------------------------------------
def _add_ohlcv_section(story, styles, ohlcv_by_symbol: dict[str, list[dict]] | None, max_rows: int = 7):
    if not ohlcv_by_symbol:
        return

    story.append(Paragraph("📉 OHLCV (extrait)", styles["section"]))
    story.append(Paragraph("Dernières bougies par symbole", styles["normal"]))
    story.append(Spacer(1, 0.2 * cm))

    def _fmt_time(x: Any) -> str:
        if x is None:
            return "-"
        s = str(x).replace("T", " ").replace("Z", "")
        return s[:16]

    for symbol, candles in ohlcv_by_symbol.items():
        if not candles:
            continue
        tail = candles[-max_rows:]

        story.append(Paragraph(f"• <b>{_safe(symbol)}</b>", styles["h3"]))

        header = ["Time", "Open", "High", "Low", "Close", "Volume"]
        data = [header]
        for c in tail:
            data.append([
                _fmt_time(c.get("time")),
                _fmt_num(c.get("open"), 3),
                _fmt_num(c.get("high"), 3),
                _fmt_num(c.get("low"), 3),
                _fmt_num(c.get("close"), 3),
                _fmt_num(c.get("volume"), 0),
            ])

        tbl = Table(data, colWidths=[3.5*cm, 2.1*cm, 2.1*cm, 2.1*cm, 2.1*cm, 3.0*cm])
        _style_table_default(tbl)
        story.append(tbl)
        story.append(Spacer(1, 0.25 * cm))



def _add_trace_quality_section(story, styles, payload: DailyPdfRequest):
    trace = payload.trace or {}

    # Quality gate peut être au root OU dans trace
    q_ok = payload.quality_ok if payload.quality_ok is not None else trace.get("quality_ok")
    q_level = _safe(payload.quality_level or trace.get("quality_level") or trace.get("quality") or "")
    q_reason = _safe(payload.quality_reason or trace.get("quality_reason") or trace.get("quality_reason_msg") or "")

    # Badge couleur
    if q_ok is True or (q_level.upper() in ("PASS", "OK")):
        q_txt, q_col = "✅ PASS", colors.HexColor("#16A34A")
    elif q_ok is False or (q_level.upper() in ("FAIL", "KO")):
        q_txt, q_col = "❌ FAIL", colors.HexColor("#DC2626")
    else:
        q_txt, q_col = "⚠ UNKNOWN", colors.HexColor("#F59E0B")

    story.append(Paragraph("🔎 Traçabilité & Qualité", styles["section"]))
    story.append(Paragraph("Audit (Add Trace) + décision (Quality Gate)", styles["normal"]))
    story.append(Spacer(1, 0.2 * cm))

    # 2 cartes : trace + quality
    run_id = _safe(trace.get("run_id") or "")
    gen_at = _pretty_dt(_safe(trace.get("generated_at") or payload.generated_at))
    workflow = _safe(trace.get("workflow") or "")
    pipeline = _safe(trace.get("pipeline") or "")
    retry_count = trace.get("retry_count", 0)

    left = Table([[
        Paragraph("<b>Add Trace</b>", ParagraphStyle("tqh", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white)),
    ], [
        Paragraph(f"<b>run_id</b> : {run_id or '-'}", styles["small"]),
    ], [
        Paragraph(f"<b>generated_at</b> : {gen_at}", styles["small"]),
    ], [
        Paragraph(f"<b>workflow</b> : {workflow or '-'}", styles["small"]),
    ], [
        Paragraph(f"<b>pipeline</b> : {pipeline or '-'}", styles["small"]),
    ], [
        Paragraph(f"<b>retry_count</b> : {retry_count}", styles["small"]),
    ]], colWidths=[7.6 * cm])

    left.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(styles["blue_dark"])),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("BOX", (0,0), (-1,-1), 0.8, colors.HexColor("#0B1220")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    right = Table([[
        Paragraph("<b>Quality Gate</b>", ParagraphStyle("tqh2", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white)),
    ], [
        _badge(f"Résultat : {q_txt}", q_col),
    ], [
        Paragraph(f"<b>quality_level</b> : {_safe(q_level) or '-'}", styles["small"]),
    ], [
        Paragraph(f"<b>quality_ok</b> : {('true' if q_ok is True else 'false' if q_ok is False else '-')}", styles["small"]),
    ], [
        Paragraph(f"<b>quality_reason</b> : {_safe(q_reason) or '-'}", styles["small"]),
    ]], colWidths=[7.6 * cm])

    right.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("BOX", (0,0), (-1,-1), 0.8, colors.HexColor("#0B1220")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))

    two = Table([[left, right]], colWidths=[7.8 * cm, 7.8 * cm])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(two)

    story.append(Spacer(1, 0.35 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.2 * cm))


# --------------------------------------------------------------------
# ✅ ROUTE PRINCIPALE FASTAPI
# --------------------------------------------------------------------
@router.post("/daily-report")
def generate_daily_report(payload: DailyPdfRequest):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="StormCopilot Daily Report",
        author="IT-STORM Consulting",
    )

    styles = _build_styles()
    story = []

    _add_cover_page(story, styles, payload.generated_at)
    _add_header(story, styles, payload.generated_at)

    _add_dashboard_page(story, styles, payload)
    # (désactivé) Résumé exécutif : on ne l'inclut plus dans le PDF
    # _add_executive_summary(story, styles, payload.human_text)
 
    _add_tech_section(story, styles, payload.tech_radar)
    _add_market_ai_table(story, styles, payload.market_ai_rows, payload.market_ai_summary)
    _add_market_assets_table(story, styles, payload.market_radar_assets)

    # ✅ AJOUT
    _add_mlops_section(story, styles, payload)
    _add_ohlcv_section(story, styles, payload.ohlcv_by_symbol, max_rows=7)
    _add_trace_quality_section(story, styles, payload)

    story.append(Spacer(1, 0.35 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph("StormCopilot – IT-STORM Consulting · Rapport généré automatiquement.", styles["small"]))

    doc.build(story)

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="stormcopilot_daily_report.pdf"'},
    )
