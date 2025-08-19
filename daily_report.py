#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report
Erstellt ein PDF in /tmp/… und gibt den Pfad aus (wird vom GitHub-Workflow weiter­verarbeitet).
"""

# --------------------------------------------------------------------------- #
# Standard-Bibliotheken
# --------------------------------------------------------------------------- #
import os, io, json, re, difflib, requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict

# --------------------------------------------------------------------------- #
# Dritte-Bibliotheken
# --------------------------------------------------------------------------- #
import pytz
from serpapi import GoogleSearch
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
def now_local() -> datetime: return datetime.now(TZ)
def debug(msg: str): print(f"[INVESTORY] {msg}")

# Secrets / Env-Variablen ---------------------------------------------------- #
LOGO_URL        = os.getenv("INV_LOGO_URL")
POPPINS_REG_URL = os.getenv("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL= os.getenv("INV_POPPINS_BOLD_URL")
OAI_KEY         = os.getenv("INV_OAI_API_KEY")
SERP_KEY        = os.getenv("SERPAPI_KEY")

# SerpAPI – definierte Medien (max 1 Credit je Suche) ------------------------ #
NEWS_SOURCES = {
    "Bloomberg":          "bloomberg.com",
    "Financial Times":    "ft.com",
    "Reuters":            "reuters.com",
    "Wall Street Journal":"wsj.com",
    "CNBC":               "cnbc.com",
    "Nikkei Asia":        "asia.nikkei.com",
    "Finanz und Wirtschaft":"fuw.ch",
    "NZZ":                "nzz.ch",
    "Handelszeitung":     "handelszeitung.ch",
    "AGEFI":              "agefi.com",          # franz. CH-Finanzportal
    "finews.ch":          "finews.ch",
    "cash.ch":            "cash.ch"
}

# --------------------------------------------------------------------------- #
# 1 | SerpAPI – News holen
# --------------------------------------------------------------------------- #
def serp_news(query: str,
              date_from: str,
              date_to: str,
              limit: int = 3) -> List[Tuple[str,str,str]]:
    """
    Liefert [(titel, url, datum)] für eine Query.
    Datum im Format YYYY-MM-DD.
    """
    if not SERP_KEY:
        debug("SERPAPI_KEY fehlt – gebe leere Liste zurück.")
        return []

    params = {
        "engine":  "google_news",
        "q":       query,
        "hl":      "de",
        "num":     limit,
        "after":   date_from,
        "before":  date_to,
        "api_key": SERP_KEY,
        "sort_by": "date"
    }
    try:
        res = GoogleSearch(params).get_dict()
        out: List[Tuple[str,str,str]] = []
        for item in res.get("news_results", []):
            out.append((item["title"], item["link"], item.get("date", "")[:10]))
        return out
    except Exception as e:
        debug(f"SerpAPI-Fehler: {e}")
        return []

def fetch_top_news(date_from: str, date_to: str) -> List[Dict]:
    """
    Holt pro Quelle max 1 relevanten Artikel und dedupliziert.
    Rückgabe: Liste dicts {source,title,url,date}
    """
    raw: List[Dict] = []
    for source, domain in NEWS_SOURCES.items():
        q = f"site:{domain} Aktien Börse {date_from}"
        art = serp_news(q, date_from, date_to, limit=1)
        if art:
            title, url, date = art[0]
            raw.append({"source": source, "title": title, "url": url, "date": date})

    # Duplikate (ähnliche Titel) entfernen, Schweiz hat Vorrang ----------------
    unique: List[Dict] = []
    for art in raw:
        is_dup = False
        for u in unique:
            ratio = difflib.SequenceMatcher(None, art["title"], u["title"]).ratio()
            if ratio >= 0.85:
                # Schweizer Quelle bevorzugen
                prefer_ch = art["source"] in ("NZZ","Finanz und Wirtschaft","Handelszeitung",
                                              "AGEFI","finews.ch","cash.ch")
                if prefer_ch: u.update(art)   # ersetzen
                is_dup = True
                break
        if not is_dup:
            unique.append(art)
    return unique

# --------------------------------------------------------------------------- #
# 2 | OpenAI – Überschriften & Summary bauen lassen
# --------------------------------------------------------------------------- #
def gen_report_data() -> Dict:
    """
    Struktur:
      {
        "headline": ["Überschrift 1", …],   # 2-5 Stk
        "articles": [
            {"title": "...", "summary": "...", "source": "...", "url": "...", "date": "...",
             "companies": ["Novartis","Sonova"]}
        ]
      }
    """
    today     = now_local().date()
    prev_day  = today - timedelta(days=1 if today.weekday() != 0 else 3)
    from_iso  = prev_day.isoformat()
    to_iso    = today.isoformat()

    top_news = fetch_top_news(from_iso, to_iso)       # max 11 Einträge
    if not top_news:
        debug("Keine News gefunden – Fallback-Inhalt.")
        return {"headline":["(Keine News gefunden)"], "articles": []}

    # Kontext für GPT ---------------------------------------------------------
    ctx_lines = []
    for n in top_news:
        ctx_lines.append(f"* {n['source']} | {n['title']} | {n['url']} | {n['date']}")
    context_news = "\n".join(ctx_lines)

    prompt = f"""
Du bist Finanzjournalist. Erstelle Headline(s) und kurze Zusammenfassungen.

**Ausgangsartikel**
{context_news}

**Aufgabe**
Für jeden Artikel:
• Formuliere eine prägnante **Überschrift** (max. 120 Zeichen).  
• Verfasse eine **Summary in 2-3 Sätzen** (max 350 Zeichen).  
• Extrahiere betroffene Unternehmens­Namen in normaler Schreibweise
  (z. B. «Novartis», «Sonova»). 0-n Einträge möglich.

**Rückgabe (JSON)**  
{{
  "headline": ["2-5 prägnante Schlagzeilen"],
  "articles": [
    {{
      "title": "…",     ← Überschrift
      "summary": "…",   ← 2-3 Sätze
      "source": "…",    ← Name wie oben
      "url": "…",       ← Deep Link
      "date": "YYYY-MM-DD",
      "companies": ["…","…"]
    }},
    …
  ]
}}

Gib **nur** den JSON-Block zurück.
Datum heute: {today.isoformat()}
"""

    # OpenAI-Call -------------------------------------------------------------
    if not OAI_KEY:
        debug("Kein OpenAI-Key – gebe rohe Titel zurück.")
        articles = [{"title": n["title"],
                     "summary": "",
                     "source": n["source"],
                     "url": n["url"],
                     "date": n["date"],
                     "companies": []} for n in top_news]
        return {"headline":["(Ohne GPT-Zusammenfassungen)"], "articles": articles}

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
        "max_tokens": 2000
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        debug(f"OpenAI-Fehler: {e}")
        # Fallback: nur Titel ohne Summary
        data = {"headline":["(OpenAI-Error)"],
                "articles":[{"title": n["title"],
                             "summary":"", **n, "companies": []} for n in top_news]}

    # Grund-Validierung -------------------------------------------------------
    data.setdefault("headline", [])
    data.setdefault("articles", [])
    return data

# --------------------------------------------------------------------------- #
# 3 | PDF-Erstellung
# --------------------------------------------------------------------------- #
def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def register_poppins() -> None:
    try:
        pdfmetrics.registerFont(TTFont("Poppins",      io.BytesIO(fetch_bytes(POPPINS_REG_URL))))
        pdfmetrics.registerFont(TTFont("Poppins-Bold", io.BytesIO(fetch_bytes(POPPINS_BOLD_URL))))
    except Exception as e:
        debug(f"Poppins nicht geladen → Helvetica ({e})")

def build_pdf(out_path: str, logo_bytes: bytes, report: Dict):
    if not isinstance(report, dict):
        report = {}
    report.setdefault("headline", [])
    report.setdefault("articles", [])

    register_poppins()
    base_font = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold_font = base_font + ("-Bold" if base_font == "Poppins" else "-Bold")

    styles = getSampleStyleSheet()
    styles["Normal"].fontName = base_font
    styles["Normal"].fontSize = 9.3
    styles["Normal"].leading  = 13

    h1 = ParagraphStyle("H1", parent=styles["Normal"],
                        fontName=bold_font, fontSize=15, leading=19,
                        alignment=2, spaceAfter=2)
    h3 = ParagraphStyle("H3", parent=styles["Normal"],
                        fontName=bold_font, fontSize=11.5, leading=15,
                        spaceBefore=6, spaceAfter=2)
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"],
                            leftIndent=10, bulletIndent=0, spaceAfter=5)

    def p_bullet(txt): return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)

    # Logo --------------------------------------------------------------------
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    logo_w = 5.0 * cm
    logo   = Image(io.BytesIO(logo_bytes), width=logo_w, height=ih * logo_w / iw)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.5*cm,  bottomMargin=1.6*cm)

    story: List = []
    story.append(Table(
        [[logo, Paragraph("Daily Investment Report", h1)]],
        colWidths=[logo_w+0.6*cm, 18*cm-(logo_w+0.6*cm)],
        style=[("VALIGN",(0,0),(-1,-1),"TOP"),
               ("ALIGN",(1,0),(1,0),"RIGHT"),
               ("LEFTPADDING",(0,0),(-1,-1),0),
               ("RIGHTPADDING",(0,0),(-1,-1),0)]
    ))
    story += [Spacer(1,4),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.7),
              Spacer(1,6)]

    # (1) Headlines -----------------------------------------------------------
    for hl in report["headline"][:5]:
        story.append(p_bullet(hl))
    story.append(Spacer(1,10))

    # (2) Artikel-Liste -------------------------------------------------------
    link_pat = re.compile(r"https?://[^ ]+")
    for art in report["articles"]:
        title = art.get("title","").strip()
        source= art.get("source","Quelle")
        url   = art.get("url","#")
        date  = art.get("date","")
        summ  = art.get("summary","").strip()
        comps = ", ".join(art.get("companies", []))
        comps = f" ({comps})" if comps else ""

        story.append(Paragraph(title, h3))
        info_line = (f"<link href='{url}' color='#0b5bd3'><u>{source}</u></link> — "
                     f"{datetime.fromisoformat(date).strftime('%d.%m.%y') if date else ''} – "
                     f"{summ}{comps}")
        story.append(Paragraph(info_line, styles["Normal"]))
        story.append(Spacer(1,4))

    story += [Spacer(1,6),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.7),
              Spacer(1,3),
              Paragraph("© INVESTORY — Alle Angaben ohne Gewähr.", styles["Normal"])]

    doc.build(story)

# --------------------------------------------------------------------------- #
# 4 | Pipeline & CLI
# --------------------------------------------------------------------------- #
def run_pdf_pipeline() -> str:
    report   = gen_report_data()
    out_path = f"/tmp/Daily_Investment_Report_{now_local().strftime('%Y-%m-%d')}.pdf"
    logo     = fetch_bytes(LOGO_URL)
    build_pdf(out_path, logo, report)
    print(out_path)          # Pfad für GitHub-Action ausgeben
    return out_path

if __name__ == "__main__":
    run_pdf_pipeline()
