#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report (Local-only)
Erzeugt ein PDF unter /tmp/… und gibt den Pfad aus,
damit der GitHub-Workflow die Datei weiterverarbeiten kann.
"""
import os, io, json, requests
from datetime import datetime, timedelta   # ← timedelta jetzt importiert
import pytz
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from serpapi import GoogleSearch

# --------------------------------------------------------------------------- #
# Konstanten & Helfer
# --------------------------------------------------------------------------- #
TZ = pytz.timezone("Europe/Zurich")
UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}
def now_local(): return datetime.now(TZ)
def debug(msg):  print(f"[INVESTORY] {msg}")

LOGO_URL        = os.environ.get("INV_LOGO_URL")
POPPINS_REG_URL = os.environ.get("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL= os.environ.get("INV_POPPINS_BOLD_URL")
OAI_KEY         = os.environ.get("INV_OAI_API_KEY")

# --------------------------------------------------------------------------- #
# Vollständige Ticker-Liste
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

# --------------------------------------------------------------------------- #
# OpenAI – erweiterter Prompt  (Stand 21-Aug-2025)
# --------------------------------------------------------------------------- #
def gen_report_data_via_openai() -> dict:
    """
    Liefert einen JSON-Marktüberblick für den Vortag
    (bei Montag: Freitag–Sonntag). Passt zur Struktur des PDF-Builders.
    """
    if not OAI_KEY:
        debug("OpenAI key missing – fallback content.")
        return {"headline":["(Fallback) Kein API-Key"],
                "sections":{k:[] for k in ("moves","news","analyst","macro","special")}}

    # ── Zeitpunkt definieren: gestern, bei Montag = Freitag (–3 Tage) ─────────
    prev_day = now_local() - timedelta(days=1 if now_local().weekday() != 0 else 3)

    # ── Prompt zusammenbauen ─────────────────────────────────────────────────
    prompt = f"""
Du bist Finanzjournalist und erstellst den **Täglichen Investment-Report**.

**Ticker-Universum**  
Analysiere ausschließlich folgende Aktien: {RELEVANT_TICKERS}

**Berücksichtigter Zeitraum**  
Alle Kursbewegungen & Nachrichten beziehen sich auf **{prev_day.strftime('%A, %d.%m.%Y')}**  
(bei Wochenstart: Freitag – Sonntag einbeziehen).

**Gliederung & Überschriften (bitte exakt übernehmen):**
1. Kursbewegungen & Marktreaktionen – Tagesbewegung > ±3 %, inkl. Kurstreiber  
2. Unternehmensnachrichten – Zahlen, Gewinnwarnungen, M&A, etc.  
3. Analystenstimmen – neue Ratings und Preisziele großer Häuser  
4. Makro / Branche – Relevante Gesetze, Rohstoff- oder Zinsbewegungen  
5. Sondermeldungen – Sanktionen oder Embargos, falls betroffen

**Regeln für Bullet-Points**
• max. 10 Punkte pro Abschnitt, jeder ≤ 3 Zeilen  
• *vor* jedem Punkt die **Original-Quelle als **vollständige Deep-Link-URL**    
• Verwende nur Links, die mindestens ein Unterverzeichnis enthalten  
  (`.../content/...`, `.../article/...`, `.../story/...` o. Ä.).  
  Ersetze sie **nicht** durch reine Homepage-Links.  
• Abschnitt komplett weglassen, wenn keine Punkte vorhanden sind  
• Keine nummerierten Bullets im Text

**Rückgabeformat (reiner JSON-Block!):**
{{
  "headline": ["2-5 prägnante Schlagzeilen"],
  "sections": {{
    "moves":   ["[Quelle](URL) : …", ...],
    "news":    [...],
    "analyst": [...],
    "macro":   [...],
    "special": [...]
  }}
}}

Gib ausschließlich diesen JSON-Block zurück.  Datum heute: {now_local().strftime('%Y-%m-%d')}
"""

    # ── OpenAI-Request ───────────────────────────────────────────────────────
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

    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()

    try:
        data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        debug(f"OpenAI-Parsing-Fehler: {e}")
        data = {"headline":["(OpenAI-Fehler)"],
                "sections":{k:[] for k in ("moves","news","analyst","macro","special")}}

    # ── Grund-Validierung ───────────────────────────────────────────────────
    data.setdefault("headline", [])
    data.setdefault("sections", {})
    for k in ("moves","news","analyst","macro","special"):
        data["sections"].setdefault(k, [])

    return data

# --------------------------------------------------------------------------- #
# Hilfsfunktionen & PDF-Erstellung
# --------------------------------------------------------------------------- #
def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content

def register_poppins() -> bool:
    try:
        open("/tmp/Poppins-Regular.ttf","wb").write(fetch_bytes(POPPINS_REG_URL))
        open("/tmp/Poppins-Bold.ttf","wb").write(fetch_bytes(POPPINS_BOLD_URL))
        pdfmetrics.registerFont(TTFont("Poppins","/tmp/Poppins-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins-Bold","/tmp/Poppins-Bold.ttf"))
        return True
    except Exception as e:
        debug(f"Poppins-Fallback → Helvetica ({e})")
        return False

def flatten_str_list(obj):
    """Flacht verschachtelte Listen ab und konvertiert alle Elemente zu str."""
    flat = []
    if isinstance(obj, (list, tuple)):
        for item in obj:
            flat.extend(flatten_str_list(item))
    elif obj is not None:
        flat.append(str(obj))
    return flat

# --------------------------------------------------------------------------- #
# SerpAPI-Helper – holt Deep-Links zu aktuellen Artikeln
# --------------------------------------------------------------------------- #
def search_news_serpapi(query: str,
                        from_date: str,
                        to_date:   str,
                        limit:     int = 3) -> list[tuple[str, str]]:
    """
    Liefert bis zu `limit` Treffer für einen Suchbegriff aus Google News.
    Rückgabe: Liste von (Titel, URL).
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        debug("SERPAPI_KEY fehlt – gebe leere Liste zurück.")
        return []

    params = {
        "engine":  "google_news",
        "q":       query,
        "hl":      "de",
        "num":     limit,
        "after":   from_date,     # ISO-Datum, z. B. 2025-08-18
        "before":  to_date,       # exklusive upper bound
        "sort_by": "date",
        "api_key": api_key
    }

    try:
        results = GoogleSearch(params).get_dict()
        return [(a["title"], a["link"])
                for a in results.get("news_results", [])]
    except Exception as e:
        debug(f"SerpAPI-Fehler bei '{query}': {e}")
        return []

def build_pdf(out_path: str, logo_bytes: bytes, report: dict):
    """
    Erstellt das PDF aus dem von OpenAI gelieferten JSON.
    Erwartete Struktur seit 19-08-2025:
      {
        "headline": [...],
        "sections": {
          "moves":   ["[Quelle](URL) : Text", ...],
          "news":    [...],
          "analyst": [...],
          "macro":   [...],
          "special": [...]
        }
      }
    """

    # 1) Fonts laden ---------------------------------------------------------
    register_poppins()
    base_font = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold_font = base_font + "-Bold" if base_font == "Poppins" else "Helvetica-Bold"

    # 2) Style-Vorlagen -------------------------------------------------------
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = base_font
    styles["Normal"].fontSize = 9.5        # 1 pt kleiner
    styles["Normal"].leading  = 13

    h2 = ParagraphStyle(
        "H2", parent=styles["Normal"],
        fontName=bold_font, fontSize=11, leading=15,     # Überschrift 1 pt kleiner
        spaceBefore=10, spaceAfter=5,                    # größerer Abstand
        textColor=colors.HexColor("#0f2a5a")
    )
    bullet = ParagraphStyle(
        "Bullet", parent=styles["Normal"],
        leftIndent=10, bulletIndent=0, spaceAfter=4
    )

    def p_bullet(txt): return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)

    # Markdown-Link ➞ HTML-Link
    import re
    md_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)\s*:\s*(.*)")
    def md_to_para(md: str) -> Paragraph:
        m = md_re.match(md)
        if m:
            label, url, text = m.groups()
            html = (f"<bullet>&#8226;</bullet>"
                    f"<link href='{url}' color='#0b5bd3'><u>{label}</u></link> : {text}")
            return Paragraph(html, bullet)
        return p_bullet(md)

    # 3) Logo + Header --------------------------------------------------------
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    logo_w = 5.0 * cm
    logo   = Image(io.BytesIO(logo_bytes), width=logo_w, height=ih * logo_w / iw)

    title_style = ParagraphStyle(
        "Title", parent=styles["Normal"],
        alignment=2, fontName=bold_font, fontSize=14.5, leading=18
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"],
        alignment=2, fontSize=8.5, textColor=colors.HexColor("#666")
    )

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.5*cm, bottomMargin=1.6*cm)

    story = []
    header = Table(
        [[logo, Paragraph("Daily Investment Report", title_style)],
         ["",   Paragraph(f"Stand: {now_local().strftime('%d.%m.%Y, %H:%M')}", meta_style)]],
        colWidths=[logo_w+0.6*cm, 18.0*cm-(logo_w+0.6*cm)]
    )
    header.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("ALIGN",(1,0),(1,0),"RIGHT"),
        ("ALIGN",(1,1),(1,1),"RIGHT"), ("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story += [header, Spacer(1,6),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,8)]

    # 4) Schlagzeilen ---------------------------------------------------------
    story.append(Paragraph("Was heute zählt", h2))
    for hl in report.get("headline", [])[:5]:
        story.append(p_bullet(hl))
    story.append(Spacer(1,8))

    # 5) Abschnitte -----------------------------------------------------------
    section_titles = {
        "moves":   "Kursbewegungen & Marktreaktionen – Tagesbewegung > ±3 %, inkl. Kurstreiber",
        "news":    "Unternehmensnachrichten – Zahlen, Gewinnwarnungen, M&A, etc.",
        "analyst": "Analystenstimmen – neue Ratings und Preisziele großer Häuser",
        "macro":   "Makro / Branche – Relevante Gesetze, Rohstoff- oder Zinsbewegungen",
        "special": "Sondermeldungen – Sanktionen oder Embargos, falls betroffen"
    }

    for key in ("moves", "news", "analyst", "macro", "special"):
        items = report.get("sections", {}).get(key, [])
        if not items:
            continue                             # Abschnitt ganz auslassen
        story.append(Paragraph(section_titles[key], h2))
        for itm in items:
            story.append(md_to_para(itm))
        story.append(Spacer(1,8))

    # 6) Footer ---------------------------------------------------------------
    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. "
                        "Keine Haftung für die Richtigkeit der Daten.", styles["Normal"])]

    # 7) PDF schreiben --------------------------------------------------------
    doc.build(story)

# --------------------------------------------------------------------------- #
# Pipeline & CLI
# --------------------------------------------------------------------------- #
def run_pdf_pipeline():
    report    = gen_report_data_via_openai()
    out_path  = f"/tmp/Daily_Investment_Report_{now_local().strftime('%Y-%m-%d')}.pdf"
    logo_data = fetch_bytes(LOGO_URL)
    build_pdf(out_path, logo_data, report)

    # >>> Diese Zeile braucht der GitHub-Workflow
    print(out_path)

    return out_path

if __name__ == "__main__":
    run_pdf_pipeline()
