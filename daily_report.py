#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report (Local-only)
➟ Einzige Änderung: Neuer Prompt für OpenAI
"""
import os, io, json, random, string, requests
from datetime import datetime
import pytz
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# --------------------------------------------------------------------------- #
# Konstanten & Helper (unverändert)
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
# Liste relevanter Ticker – wird im Prompt verwendet
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
# OpenAI – nur der Prompt ist geändert
# --------------------------------------------------------------------------- #
def gen_report_data_via_openai() -> dict:
    if not OAI_KEY:
        debug("OpenAI key missing → using fallback content.")
        return {"headline": ["(Fallback) Kein API-Key vorhanden."],
                "regions": {k: {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]} for k in ("CH","EU","US","AS")}}

    prompt = f"""
Du bist Finanzjournalist und schreibst den **Täglichen Investment-Report**.

**Ticker-Universum**  
Analysiere ausschließlich folgende Aktien (Ticker, kommasepariert):  
{RELEVANT_TICKERS}

**Inhalt pro Report (Deutsch):**
• **Kursbewegungen & Marktreaktionen** – Aktientitel mit Tagesbewegung > ±3 % (inkl. Kurstreiber: Unternehmensnews, Analysten-Ratings, Makro-Meldungen).  
• **Unternehmensnachrichten** – neue Quartalszahlen, Gewinnwarnungen, Dividenden, Managementwechsel, M&A-Deals.  
• **Analystenstimmen** – nur relevante neue Ratings/Preisziel-Änderungen großer Häuser.  
• **Branchen & Makro-Impulse** – Gesetzes-/Regulierungsnews, Rohstoff- oder Zinsbewegungen, falls eine der Firmen stark betroffen ist.  
• **Sondermeldungen** – Sanktionen/Embargos, sofern zutreffend.

**Format (JSON!):**
{{
  "headline": ["2-5 übergreifende Schlagzeilen"],
  "regions": {{
    "CH": {{"tldr":[], "moves":[], "news":[["Kurztext","https://..."]], "analyst":[], "macro":[]}},
    "EU": {{"tldr":[], "moves":[], "news":[], "analyst":[], "macro":[]}},
    "US": {{"tldr":[], "moves":[], "news":[], "analyst":[], "macro":[]}},
    "AS": {{"tldr":[], "moves":[], "news":[], "analyst":[], "macro":[]}}
  }}
}}

**Regeln:**  
- Gib **nur JSON** zurück, genau wie oben – keine Erklärungen außen herum.  
- Bullet-Inhalte pro Aktie maximal 3 Zeilen.  
- Jede News enthält, wenn möglich, eine Quelle-URL.  
- Wenn keine relevanten Infos, entsprechende Felder leer lassen.  
- Keine Halluzinationen: nur plausible, tagesaktuelle Fakten.

**Aktuelles Datum:** {now_local().strftime('%Y-%m-%d')}
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
    debug("OpenAI request → chat.completions")
    r = requests.post(url, headers=headers, json=body, timeout=60)
    debug(f"OpenAI status: {r.status_code}")
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(content)
        debug(f"OpenAI JSON parsed. Headlines: {len(parsed.get('headline', []))}")
    except Exception as e:
        debug(f"OpenAI response not JSON → fallback. Reason: {e}")
        parsed = {"headline": ["(OpenAI-Fehler) Marktüberblick nicht verfügbar."],
                  "regions": {k: {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]} for k in ("CH","EU","US","AS")}}
    return parsed

# --------------------------------------------------------------------------- #
# Alles Weitere (PDF-Erstellung etc.) ↓ bleibt unverändert
# --------------------------------------------------------------------------- #
# … (kein weiterer Code geändert; deine vorherige Version bleibt erhalten)
