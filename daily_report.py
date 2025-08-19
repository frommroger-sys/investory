#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report (Local-only)
Erzeugt ein PDF unter /tmp/… und gibt den Pfad aus,
damit der GitHub-Workflow die Datei weiterverarbeiten kann.
"""
import os, io, json, requests
from datetime import datetime
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
# OpenAI – erweiterter Prompt
# --------------------------------------------------------------------------- #
def gen_report_data_via_openai() -> dict:
    if not OAI_KEY:
        debug("OpenAI key missing – fallback-Inhalt.")
        return {"headline": ["(Fallback) Kein API-Key."],
                "regions": {k: {"tldr": [], "moves": [], "news": [],
                                "analyst": [], "macro": []}
                            for k in ("CH", "EU", "US", "AS")}}

    prompt = f"""
Du bist Finanzjournalist und schreibst den **Täglichen Investment-Report**.

**Ticker-Universum**  
Analysiere ausschließlich folgende Aktien (commasepariert):  
{RELEVANT_TICKERS}

**Inhalt pro Report (Deutsch):**
• **Kursbewegungen & Marktreaktionen** – Tagesbewegung > ±3 %, inkl. Kurstreiber  
• **Unternehmensnachrichten** – Zahlen, Gewinnwarnungen, Dividenden, M&A, Mgmt-Wechsel  
• **Analystenstimmen** – neue Ratings/Preisziele großer Häuser  
• **Makro/Branche** – Relevante Gesetze, Rohstoff- oder Zinsbewegungen  
• **Sondermeldungen** – Sanktionen/Embargos falls betroffen

**Rückgabeformat (JSON!):**
{{
  "headline": ["2-5 Schlagzeilen"],
  "regions": {{
    "CH": {{"tldr":[],"moves":[],"news":[["Kurztext","https://…"]],"analyst":[],"macro":[]}},
    "EU": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}},
    "US": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}},
    "AS": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}}
  }}
}}

Regeln: Gib **nur JSON** zurück. Keine Halluzinationen.  
Datum: {now_local().strftime('%Y-%m-%d')}
"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OAI_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Du bist ein präziser Finanzredakteur."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1400
    }
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    try:
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        debug(f"OpenAI-Fehler: {e}")
        return {"headline":["(OpenAI-Fehler)"],"regions":{k:{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]} for k in ("CH","EU","US","AS")}}

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

def build_pdf(out_path: str, logo_bytes: bytes, report: dict):
    register_poppins()
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading  = 14

    title_style = ParagraphStyle("TitleRight", parent=styles["Normal"],
                                 alignment=2, fontName=styles["Normal"].fontName,
                                 fontSize=14.5, leading=18, textColor=colors.HexColor("#111"))
    meta_style  = ParagraphStyle("Meta", parent=styles["Normal"],
                                 alignment=2, fontSize=9.5, textColor=colors.HexColor("#666"))
    h2   = ParagraphStyle("H2", parent=styles["Normal"],
                          fontName=styles["Normal"].fontName,
                          fontSize=12.2, leading=16,
                          spaceBefore=6, spaceAfter=3,
                          textColor=colors.HexColor("#0f2a5a"))
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"],
                            leftIndent=10, bulletIndent=0, spaceAfter=3)

    def p_bullet(txt): return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)
    def p_link(txt, url): return Paragraph(f"<bullet>&#8226;</bullet>{txt} "
                                           f"<font color='#0b5bd3'><u><link href='{url}'>Quelle</link></u></font>",
                                           bullet)

    # Header
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    scale = (3.2 * cm) / iw
    logo  = Image(io.BytesIO(logo_bytes), width=iw * scale, height=ih * scale)
    title = Paragraph("Daily Investment Report", title_style)
    stamp = Paragraph(f"Stand: {now_local().strftime('%d.%m.%Y, %H:%M')}", meta_style)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.5*cm, bottomMargin=1.6*cm)
    story = []
    hdr   = Table([[logo, title], ["", stamp]],
                  colWidths=[3.8*cm, 18.0*cm-3.8*cm])
    hdr.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("ALIGN",(1,0),(1,0),"RIGHT"),
        ("ALIGN",(1,1),(1,1),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story += [hdr, Spacer(1,6),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,8)]

    story += [Paragraph("Was heute zählt", h2)]
    for s in report.get("headline", [])[:5]:
        story.append(p_bullet(s))
    story.append(Spacer(1,8))

    def region(title, key):
        data = report.get("regions", {}).get(key, {})
        story.append(Paragraph(title, h2))
        if data.get("tldr"):
            story.append(p_bullet("<b>TL;DR:</b> " + "; ".join(data["tldr"])[:400]))
        if data.get("moves"):
            story.append(p_bullet("<b>Top Moves:</b> " + "; ".join(data["moves"])[:400]))
        for item in (data.get("news") or [])[:8]:
            if isinstance(item,(list,tuple)) and len(item)==2:
                txt,url=item
                story.append(p_link(f"<b>Unternehmensnews:</b> {txt}", url))
        if data.get("analyst"):
            story.append(p_bullet("<b>Analysten:</b> " + "; ".join(data["analyst"])[:400]))
        if data.get("macro"):
            story.append(p_bullet("<b>Makro/Branche:</b> " + " ".join(data["macro"])[:400]))
        story.append(Spacer(1,6))

    region("1) Schweiz (SIX)", "CH")
    region("2) Europa",        "EU")
    region("3) USA",           "US")
    region("4) Asien",         "AS")

    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. Keine Haftung für die Richtigkeit der Daten.",
                        styles["Normal"])]

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
