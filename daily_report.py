#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report (Local-only)
Erzeugt ein PDF unter /tmp/… und gibt den Pfad aus,
damit der GitHub-Workflow die Datei weiterverarbeiten kann.
"""
# --------------------------------------------------------------------------- #
# Standard-Bibliotheken
# --------------------------------------------------------------------------- #
import os, io, json, re, requests
from datetime import datetime, timedelta
import pytz

# --------------------------------------------------------------------------- #
# ReportLab
# --------------------------------------------------------------------------- #
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# --------------------------------------------------------------------------- #
# SerpAPI
# --------------------------------------------------------------------------- #
from serpapi import GoogleSearch

# --------------------------------------------------------------------------- #
# Konstanten & Helfer
# --------------------------------------------------------------------------- #
TZ = pytz.timezone("Europe/Zurich")
def now_local() -> datetime:               # aktuelle Zeit in Zürich
    return datetime.now(TZ)

def debug(msg: str):
    print(f"[INVESTORY] {msg}")

UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}

# Secrets / URLs aus GitHub-Actions
LOGO_URL         = os.getenv("INV_LOGO_URL")
POPPINS_REG_URL  = os.getenv("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL = os.getenv("INV_POPPINS_BOLD_URL")
OAI_KEY          = os.getenv("INV_OAI_API_KEY")

# --------------------------------------------------------------------------- #
# Vollständige Ticker-Liste (vorerst nicht gekürzt)
# --------------------------------------------------------------------------- #
RELEVANT_TICKERS = """
SIKA.SW, ROG.SW, VETN.SW, SOON.SW, SFZN.SW, UBSG.SW, PM.SW, LISN.SW,
UHRN.SW, NHY.OL, RIEN.SW, KNIN.SW, ULTA, SGSN.SW, AD.AS, SRAIL.SW,
ADYEN.AS, ASCN.SW, LIGHT.AS, KOMN.SW, STMN.SW, ADEN.SW, DRX.L, ARYN.SW,
6988.T, FORN.SW, ZTS, TECN.SW, 4528.T, NOVO-B.CO, LOTB.BR, EQNR.OL, PBR,
ORON.SW, GURN.SW, VACN.SW, RO.SW, TOM.OL, IMB.L, KGX.DE, ODD, RMS.PA,
GALE.SW, FHZN.SW, ABBN.SW, LAND.SW, NOC, SREN.SW, AMS.SW, BION.SW,
STGN.SW, NESN.SW, HOLN.SW, MYM.DE, SALRY, EVN.VI, DPW.DE, LIN.DE,
NOVN.SW, ZURN.SW, LIN, VATN.SW, NFLX, SLHN.SW, LHX, ALLN.SW, GMI.SW,
CMBN.SW, HELN.SW, JFN.SW, SCMN.SW, BKW.SW, LEON.SW, PGHN.SW, 1TY.DE,
SAIRGROUP N, SUNRISE N, AMRZ.SW, FTNT, ACN, ADBE, ASML.AS, QCOM, BC94.L,
ADSK, QLYS, SYNA, 6861.T, ACMR, 2330.TW, GOOG, META, PANW, NOW, NVDA,
MSFT, TSLA, PLTR, 9999.HK, KLAC, ISRG, AMZN, 0700.HK, 81810.HK, ZS, AVGO,
ROK, CLS, MRVL, DUOL, INTU, FRSH, PGYWW, COMM, LULU, FAST, TTD, ASML, PEP,
PYPL, AMD, CMCSA, REGN, DXCM, ODFL, ANSS, MDLZ, GOOGL, GILD, CHTR, IDXX,
MNST, EA, ROST, CSX
""".replace("\n", " ").strip()

# =========================================================================== #
# 1. SERP-API-HELFER
# =========================================================================== #
def search_news_serpapi(query: str,
                        from_date: str,
                        to_date:   str,
                        limit:     int = 10) -> list[tuple[str, str]]:
    """
    Holt bis zu `limit` News-Treffer (Titel, URL) via Google News / SerpAPI.
    Rückgabe: Liste [(title, url), …] – bei Fehlern leere Liste.
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        debug("SERPAPI_KEY fehlt – leere Trefferliste")
        return []

    params = {
        "engine":  "google_news",
        "q":       query,
        "hl":      "de",
        "num":     limit,
        "after":   from_date,   # einschl.
        "before":  to_date,     # exklusiv
        "sort_by": "date",
        "api_key": api_key
    }

    try:
        res = GoogleSearch(params).get_dict()
        return [(a["title"], a["link"])
                for a in res.get("news_results", [])]
    except Exception as e:
        debug(f"SerpAPI-Fehler bei »{query}«: {e}")
        return []

def fetch_top_news(from_iso: str,
                   to_iso:   str,
                   limit_per_query: int = 15) -> list[tuple[str, str]]:
    """
    Drei breite Suchanfragen (intl., US, CH) → vereint, Duplikate entfernt.
    """
    queries = [
        # 1) Internationale Leitmedien
        "site:bloomberg.com OR site:ft.com OR site:reuters.com stocks today",
        # 2) US-Tech & Makro
        "site:cnbc.com OR site:wsj.com market today",
        # 3) Schweiz / D-A-CH
        "site:nzz.ch OR site:fuw.ch OR site:handelszeitung.ch börse heute"
    ]

    hits: list[tuple[str, str]] = []
    for q in queries:
        hits += search_news_serpapi(q, from_iso, to_iso, limit_per_query)

    # Duplikate (gleiche URL) entfernen
    seen, unique = set(), []
    for title, url in hits:
        if url not in seen:
            unique.append((title, url))
            seen.add(url)

    return unique[:40]   # hartes Limit für den Prompt

# =========================================================================== #
# 2. OPENAI-ABFRAGE
# =========================================================================== #
def gen_report_data_via_openai() -> dict:
    """
    Fragt GPT-4o mini nach einem Markt-Überblick und gibt IMMER
    ein gültiges Dict im erwarteten Format zurück.
    """
    if not OAI_KEY:
        debug("OpenAI-Key fehlt – Fallback-Inhalt")
        return {"headline": ["(Kein OpenAI-Key)"],
                "sections": {k: [] for k in ("moves","news","analyst","macro","special")}}

    # -------- Zeitraum: Vortag (Mo = Freitag) -------------------------------
    today    = now_local().date()
    prev_day = today - timedelta(days=1 if today.weekday() != 0 else 3)
    from_iso = prev_day.isoformat()
    to_iso   = today.isoformat()

    # -------- Top-News per SerpAPI ------------------------------------------
    top_news = fetch_top_news(from_iso, to_iso)
    context_news = "\n".join(f"* {title} | {url}" for title, url in top_news)

    # -------- Prompt --------------------------------------------------------
    prompt = f"""
Du bist Finanzjournalist und erstellst den **Täglichen Investment-Report**.

**Ticker-Universum**  
Analysiere ausschließlich folgende Aktien: {RELEVANT_TICKERS}

**Originalartikel (Titel | URL)**  
{context_news}

**Berücksichtigter Zeitraum**  
Alle Kursbewegungen & Nachrichten beziehen sich auf **{prev_day.strftime('%A, %d.%m.%Y')}**  
(bei Wochenstart: Freitag – Sonntag einbeziehen).

**Gliederung (bitte exakt nutzen):**
1. Kursbewegungen & Marktreaktionen – Tagesbewegung > ±3 %, inkl. Kurstreiber  
2. Unternehmensnachrichten – Zahlen, Gewinnwarnungen, M&A, etc.  
3. Analystenstimmen – neue Ratings und Preisziele großer Häuser  
4. Makro / Branche – Relevante Gesetze, Rohstoff- oder Zinsbewegungen  
5. Sondermeldungen – Sanktionen oder Embargos, falls betroffen

**Regeln für Bullet-Points**
• max. 10 Punkte je Abschnitt, jeder ≤ 3 Zeilen  
• vor jedem Punkt die **Deep-Link-URL** der Quelle (`https://…/article/...`)  
• Abschnitte ohne Punkte komplett weglassen  
• keine nummerierten Bullets im Text

**Rückgabeformat (reiner JSON-Block!):**
{{
  "headline": ["2-5 prägnante Schlagzeilen"],
  "sections": {{
    "moves":   ["[Quelle](URL) : …", …],
    "news":    […],
    "analyst": […],
    "macro":   […],
    "special": […]
  }}
}}

Gib **ausschließlich** diesen JSON-Block zurück.  Datum: {today}
"""

    # -------- OpenAI-Request -----------------------------------------------
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OAI_KEY}",
               "Content-Type":  "application/json"}
    body = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Du bist ein präziser Finanzredakteur."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1600
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        debug(f"OpenAI-Fehler: {e}")
        data = {"headline": ["(OpenAI-Error)"],
                "sections": {k: [] for k in ("moves","news","analyst","macro","special")}}

    # -------- Minimal-Validierung ------------------------------------------
    data.setdefault("headline", [])
    data.setdefault("sections", {})
    for k in ("moves","news","analyst","macro","special"):
        data["sections"].setdefault(k, [])

    return data

# =========================================================================== #
# 3. PDF-ERSTELLUNG
# =========================================================================== #
def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content

def register_poppins() -> None:
    try:
        open("/tmp/Poppins-Regular.ttf","wb").write(fetch_bytes(POPPINS_REG_URL))
        open("/tmp/Poppins-Bold.ttf","wb").write(fetch_bytes(POPPINS_BOLD_URL))
        pdfmetrics.registerFont(TTFont("Poppins",      "/tmp/Poppins-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins-Bold", "/tmp/Poppins-Bold.ttf"))
    except Exception as e:
        debug(f"Poppins-Fallback auf Helvetica ({e})")

def build_pdf(out_path: str, logo_bytes: bytes, report: dict) -> None:
    """
    Baut das PDF.  `report` kommt aus gen_report_data_via_openai().
    """
    # ----- Safety-Net -------------------------------------------------------
    if not isinstance(report, dict):
        report = {}
    report.setdefault("headline", [])
    report.setdefault("sections", {})

    # ----- Fonts & Styles ---------------------------------------------------
    register_poppins()
    base_font = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold_font = "Poppins-Bold" if base_font == "Poppins" else "Helvetica-Bold"

    styles = getSampleStyleSheet()
    styles["Normal"].fontName = base_font
    styles["Normal"].fontSize = 9.5
    styles["Normal"].leading  = 13

    h2 = ParagraphStyle("H2", parent=styles["Normal"],
                        fontName=bold_font, fontSize=11, leading=15,
                        spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#0f2a5a"))
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"],
                            leftIndent=10, bulletIndent=0, spaceAfter=4)

    def p_bullet(txt: str) -> Paragraph:
        return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)

    md_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)\s*:\s*(.*)")

    def md_to_para(md: str) -> Paragraph:
        m = md_re.match(md)
        if m:
            label, url, text = m.groups()
            html = (f"<bullet>&#8226;</bullet>"
                    f"<link href='{url}' color='#0b5bd3'><u>{label}</u></link> : {text}")
            return Paragraph(html, bullet)
        return p_bullet(md)

    # ----- Header ----------------------------------------------------------
    logo_img = ImageReader(io.BytesIO(logo_bytes))
    iw, ih   = logo_img.getSize()
    logo_w   = 5.0 * cm                        # fixes Maß
    logo     = Image(io.BytesIO(logo_bytes), width=logo_w, height=ih * logo_w / iw)

    title_style = ParagraphStyle("Title", parent=styles["Normal"],
                                 alignment=2, fontName=bold_font,
                                 fontSize=14.5, leading=18)
    meta_style  = ParagraphStyle("Meta",  parent=styles["Normal"],
                                 alignment=2, fontSize=8.5, textColor="#666")

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.5*cm, bottomMargin=1.6*cm)
    story: list = []

    header_tbl = Table(
        [[logo, Paragraph("Daily Investment Report", title_style)],
         ["",   Paragraph(f"Stand: {now_local().strftime('%d.%m.%Y, %H:%M')}", meta_style)]],
        colWidths=[logo_w+0.6*cm, 18.0*cm-(logo_w+0.6*cm)]
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ALIGN",(1,0),(1,0),"RIGHT"),
        ("ALIGN",(1,1),(1,1),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    story += [header_tbl, Spacer(1,6),
              HRFlowable(color="#e6e6e6", thickness=0.6),
              Spacer(1,8)]

    # ----- Schlagzeilen ----------------------------------------------------
    story.append(Paragraph("Was heute zählt", h2))
    for hl in report.get("headline", [])[:5]:
        story.append(p_bullet(hl))
    story.append(Spacer(1,8))

    # ----- Abschnitte ------------------------------------------------------
    section_titles = {
        "moves":   "Kursbewegungen & Marktreaktionen – Tagesbewegung > ±3 %, inkl. Kurstreiber",
        "news":    "Unternehmensnachrichten – Zahlen, Gewinnwarnungen, M&A, etc.",
        "analyst": "Analystenstimmen – neue Ratings und Preisziele großer Häuser",
        "macro":   "Makro / Branche – Relevante Gesetze, Rohstoff- oder Zinsbewegungen",
        "special": "Sondermeldungen – Sanktionen oder Embargos, falls betroffen"
    }

    for key in ("moves","news","analyst","macro","special"):
        items = report.get("sections", {}).get(key, [])
        if not items:
            continue
        story.append(Paragraph(section_titles[key], h2))
        for itm in items:
            story.append(md_to_para(itm))
        story.append(Spacer(1,8))

    # ----- Footer ----------------------------------------------------------
    story += [HRFlowable(color="#e6e6e6", thickness=0.6),
              Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. "
                        "Keine Haftung für die Richtigkeit der Daten.",
                        styles["Normal"])]

    # ----- PDF schreiben ---------------------------------------------------
    doc.build(story)

# =========================================================================== #
# 4. PIPELINE-EINTRITTSPUNKT
# =========================================================================== #
def run_pdf_pipeline() -> str:
    report   = gen_report_data_via_openai()
    out_path = f"/tmp/Daily_Investment_Report_{now_local().strftime('%Y-%m-%d')}.pdf"
    logo_bin = fetch_bytes(LOGO_URL)
    build_pdf(out_path, logo_bin, report)

    # → Der GitHub-Workflow liest diese Zeile aus dem Log
    print(out_path)
    return out_path

if __name__ == "__main__":
    run_pdf_pipeline()
