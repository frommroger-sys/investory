#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report (Local-only)
Erzeugt ein PDF unter /tmp/… und gibt den Pfad aus,
damit der GitHub-Workflow die Datei weiterverarbeiten kann.
"""

import os, io, json, re, requests
from datetime import datetime, timedelta
import pytz
from urllib.parse import urlparse

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# SerpAPI: robuster Import (neue/alte Paketstruktur)
try:
    from serpapi.google_search import GoogleSearch
except Exception:
    from serpapi import GoogleSearch  # Fallback, falls alte Struktur

# --------------------------------------------------------------------------- #
# Konstanten & Helfer
# --------------------------------------------------------------------------- #
TZ = pytz.timezone("Europe/Zurich")
UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}
def now_local(): return datetime.now(TZ)
def debug(msg):  print(f"[INVESTORY] {msg}")

LOGO_URL         = os.environ.get("INV_LOGO_URL")
POPPINS_REG_URL  = os.environ.get("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL = os.environ.get("INV_POPPINS_BOLD_URL")
OAI_KEY          = os.environ.get("INV_OAI_API_KEY")
SERPAPI_KEY      = os.environ.get("SERPAPI_KEY")

# Quellen-Set (Schweizer Quellen bevorzugen)
CH_DOMAINS = {"fuw.ch", "nzz.ch", "handelszeitung.ch", "agefi.com", "finews.ch", "cash.ch"}
ALL_SOURCES_QUERIES = [
    # Schweizer Quellen
    "site:fuw.ch",
    "site:nzz.ch",
    "site:handelszeitung.ch",
    "site:agefi.com",
    "site:finews.ch",
    "site:cash.ch",
    # Internationale Leitmedien
    "site:reuters.com",
    "site:bloomberg.com",
    "site:ft.com",
    "site:wsj.com",
    "site:asia.nikkei.com",
]

# --------------------------------------------------------------------------- #
# Vollständige Ticker-Liste (wird aktuell NICHT zur Erkennung genutzt)
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
# SerpAPI – News-Suche & Aufbereitung
# --------------------------------------------------------------------------- #
def serpapi_news(query: str, after_iso: str, before_iso: str, num: int = 10) -> list[dict]:
    """
    Liefert News-Treffer mit Feldern: title, link, source, date (YYYY-MM-DD), hostname.
    Filtert strikt auf Datum (nur published am Vortag-Fenster).
    """
    if not SERPAPI_KEY:
        debug("SERPAPI_KEY fehlt – gebe leere Liste zurück.")
        return []

    params = {
        "engine":  "google_news",
        "q":       query,
        "hl":      "de",
        "num":     max(1, min(num, 20)),
        "after":   after_iso,   # inkl. after (00:00)
        "before":  before_iso,  # exklusiv before (00:00 des Folgetags)
        "sort_by": "date",
        "api_key": SERPAPI_KEY,
    }

    try:
        res = GoogleSearch(params).get_dict()
        items = []
        for a in res.get("news_results", []) or []:
            title = a.get("title") or ""
            link  = a.get("link") or ""
            src   = (a.get("source") or "").strip()
            # SerpAPI liefert oft "date" oder "date_published"
            raw_date = (a.get("date") or a.get("date_published") or "").strip()

            # Datum robust normalisieren (YYYY-MM-DD) – wenn nicht belegbar, skip
            pub_date = normalize_serpapi_date(raw_date)
            if not pub_date:
                # manche Treffer ohne Datum – sicherheitshalber verwerfen
                continue

            # harte Filterung aufs Fenster
            if not is_date_in_window(pub_date, after_iso, before_iso):
                continue

            hostname = urlparse(link).hostname or ""
            hostname = hostname.replace("www.", "")
            items.append({
                "title": title.strip(),
                "link":  link.strip(),
                "source": src if src else hostname,
                "date":  pub_date,  # YYYY-MM-DD
                "hostname": hostname,
            })
        return items
    except Exception as e:
        debug(f"SerpAPI-Fehler: {e}")
        return []

def normalize_serpapi_date(raw: str) -> str | None:
    """
    Versucht SerpAPI-Datumsstrings in YYYY-MM-DD zu überführen.
    Beispiele: 'Aug 18, 2025', '18.08.25', '2 hours ago' → wird mit Vortags-Fenster schon begrenzt,
    hier nehmen wir relative Angaben als 'unknown' (None).
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    # ISO direkt?
    m = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    if m:
        return raw[:10]

    # DE-Format 18.08.25 oder 18.08.2025
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{2,4})$", raw)
    if m:
        d, mth, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{mth}-{d}"

    # Engl. Monat-Format Aug 18, 2025
    try:
        dt = datetime.strptime(raw, "%b %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Relativangaben (x hours ago) → unzuverlässig; hier None
    if "ago" in raw.lower():
        return None

    return None

def is_date_in_window(pub_date_iso: str, after_iso: str, before_iso: str) -> bool:
    """True, wenn after_iso <= pub_date < before_iso (alle im Format YYYY-MM-DD)."""
    try:
        d  = datetime.strptime(pub_date_iso, "%Y-%m-%d").date()
        a  = datetime.strptime(after_iso,     "%Y-%m-%d").date()
        b  = datetime.strptime(before_iso,    "%Y-%m-%d").date()
        return a <= d < b
    except Exception:
        return False

def fetch_top_news_window(after_iso: str, before_iso: str, per_query: int = 10) -> list[dict]:
    """
    Holt Top-News aus 11 Quellen (je Query), filtert, dedupliziert, priorisiert CH-Domains.
    Rückgabe: Liste Dicts {title, link, source, date, hostname}
    """
    all_hits: list[dict] = []
    for q in ALL_SOURCES_QUERIES:
        all_hits.extend(serpapi_news(q, after_iso, before_iso, num=per_query))

    if not all_hits:
        return []

    # Deduping: zuerst nach normalisiertem Titel (lower, ohne Klammerzusätze)
    def norm_title(t: str) -> str:
        t = t.lower().strip()
        t = re.sub(r"[\(\[\{].*?[\)\]\}]", "", t)  # Klammerinhalte raus
        t = re.sub(r"\s+", " ", t)
        return t

    buckets: dict[str, dict] = {}
    for it in all_hits:
        key = norm_title(it["title"])
        # Falls bereits vorhanden, nimm CH-Domain bevorzugt; sonst die – neuere? (Datum gleich)
        if key not in buckets:
            buckets[key] = it
        else:
            old = buckets[key]
            old_ch = old["hostname"].replace("www.", "") in CH_DOMAINS
            new_ch = it["hostname"].replace("www.", "") in CH_DOMAINS
            if new_ch and not old_ch:
                buckets[key] = it  # Schweiz gewinnt
            # sonst: lassen wir den ersten stehen

    deduped = list(buckets.values())

    # Sortierung: CH-Quellen zuerst, danach alphabetisch nach Source + Titel
    def sort_key(it):
        is_ch = it["hostname"] in CH_DOMAINS
        return (0 if is_ch else 1, it["source"].lower(), it["title"].lower())

    deduped.sort(key=sort_key)
    return deduped

# --------------------------------------------------------------------------- #
# OpenAI – Artikel zusammenfassen (Titel/Quelle/Datum/URL → 2–4 Sätze + Firmen)
# --------------------------------------------------------------------------- #
def summarize_articles_openai(items: list[dict]) -> dict:
    """
    Input: items = [{title, link, source, date, hostname}, ...]
    Output:
    {
      "articles": [
        {
          "title": "...",                     # (wie Input)
          "source": "...",                    # (wie Input)
          "url": "...",                       # (wie Input)
          "date": "YYYY-MM-DD",               # (wie Input)
          "summary": "2–4 Sätze …",
          "companies": ["Novartis","Sonova"]  # aus Text, so geschrieben wie im Artikel
        }, ...
      ]
    }
    """
    if not OAI_KEY:
        debug("OpenAI key missing – gebe Fallback-Struktur zurück.")
        return {"articles": [
            {"title": it["title"], "source": it["source"], "url": it["link"],
             "date": it["date"], "summary": "(Kein OpenAI-Key) – Rohlink.",
             "companies": []}
            for it in items[:10]
        ]}

    # Kompakter, aber eindeutiger Prompt
    catalog = "\n".join(
        f"- {it['title']} | {it['source']} | {it['date']} | {it['link']}"
        for it in items[:20]  # Safety-Limit fürs Token-Budget
    )

    prompt = f"""
Lies die folgenden Artikel (Titel | Quelle | Datum | URL) und gib für jeden eine prägnante,
journalistische Zusammenfassung mit **2–4 Sätzen** zurück. 
Am Ende der Zusammenfassung in Klammern die **Namen der im Artikel genannten Unternehmen**
(genau so geschrieben wie im Artikel, keine Tickersymbole). Wenn keine eindeutig, dann leer lassen.

Gib das Ergebnis als **reinen JSON-Block** im Format:
{{
  "articles": [
    {{
      "title": "...", "source": "...", "url": "...", "date": "YYYY-MM-DD",
      "summary": "…", "companies": ["…","…"]
    }}, ...
  ]
}}

Artikel:
{catalog}
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OAI_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Du bist ein präziser Finanzredakteur."},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        raw = r.json()
        data = json.loads(raw["choices"][0]["message"]["content"])
        # Grundvalidierung
        arts = data.get("articles", [])
        if not isinstance(arts, list):
            arts = []
        # Fülle fehlende Felder aus Originalen
        by_url = {it["link"]: it for it in items}
        normalized = []
        for a in arts:
            src = a.get("source") or ""
            url_ = a.get("url") or a.get("link") or ""
            it0 = by_url.get(url_, {})
            normalized.append({
                "title":   a.get("title")   or it0.get("title", ""),
                "source":  src or it0.get("source", ""),
                "url":     url_ or it0.get("link", ""),
                "date":    a.get("date")    or it0.get("date", ""),
                "summary": a.get("summary") or "",
                "companies": a.get("companies") if isinstance(a.get("companies"), list) else [],
            })
        return {"articles": normalized}
    except Exception as e:
        debug(f"OpenAI-Fehler (fange alles ab): {e}")
        # Fallback: Rohdaten ohne Summary
        return {"articles": [
            {"title": it["title"], "source": it["source"], "url": it["link"],
             "date": it["date"], "summary": "", "companies": []}
            for it in items[:10]
        ]}

# --------------------------------------------------------------------------- #
# Report-Daten zusammenstellen (neue Struktur)
# --------------------------------------------------------------------------- #
def gen_report_data() -> dict:
    """
    Baut die Daten für das PDF:
      { "articles": [ {title, source, url, date, summary, companies}, ... ] }
    Nur Vortag (Mo: Fr–So).
    """
    # Zeitraum bestimmen (lokal CH)
    today = now_local().date()
    prev_day = today - timedelta(days=1 if today.weekday() != 0 else 3)  # Mo→Fr (–3)
    after_iso  = prev_day.isoformat()
    before_iso = today.isoformat()

    # Top-News ziehen (11 Queries, deduped, CH bevorzugt)
    items = fetch_top_news_window(after_iso, before_iso, per_query=10)

    if not items:
        debug("Keine Items aus SerpAPI – Rückfall auf leere Artikelliste.")
        return {"articles": []}

    # OpenAI: 2–4 Sätze Summary + Companies
    summary_pack = summarize_articles_openai(items)

    # Letzte Sicherheit: Struktur
    arts = summary_pack.get("articles", [])
    if not isinstance(arts, list):
        arts = []
    # Filter: falls doch mal Altlasten hineinrutschen, erneut striktes Fenster
    arts = [a for a in arts if is_date_in_window(a.get("date",""), after_iso, before_iso)]

    return {"articles": arts}

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

# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def build_pdf(out_path: str, logo_bytes: bytes, report: dict):
    """
    Baut das PDF aus der neuen Struktur:
      { "articles": [ {title, source, url, date, summary, companies}, ... ] }
    """

    # Safety-Net: garantiert gültiges Dict
    if not isinstance(report, dict):
        report = {}
    articles = report.get("articles", [])
    if not isinstance(articles, list):
        articles = []

    # 1) Fonts ---------------------------------------------------------------
    register_poppins()
    base_font = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold_font = base_font + "-Bold" if base_font == "Poppins" else "Helvetica-Bold"

    # 2) Styles --------------------------------------------------------------
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = base_font
    styles["Normal"].fontSize = 10
    styles["Normal"].leading  = 14

    h_title = ParagraphStyle(
        "H_Title", parent=styles["Normal"],
        fontName=bold_font, fontSize=13.5, leading=17, spaceBefore=10, spaceAfter=6,
        textColor=colors.HexColor("#0f2a5a")
    )
    meta_line = ParagraphStyle(
        "Meta", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#555"), spaceAfter=4
    )
    body = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, leading=14, spaceAfter=10
    )

    # 3) Header --------------------------------------------------------------
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    logo_w = 5.0 * cm
    logo   = Image(io.BytesIO(logo_bytes), width=logo_w, height=ih * logo_w / iw)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.5*cm, bottomMargin=1.6*cm)

    story = []
    title_style = ParagraphStyle(
        "Title", parent=styles["Normal"],
        alignment=2, fontName=bold_font, fontSize=14.5, leading=18
    )
    meta_style = ParagraphStyle(
        "MetaRTL", parent=styles["Normal"],
        alignment=2, fontSize=8.5, textColor=colors.HexColor("#666")
    )

    header = Table(
        [[logo, Paragraph("Daily Investment Report", title_style)],
         ["",   Paragraph(f"Stand: {now_local().strftime('%d.%m.%Y, %H:%M')}", meta_style)]],
        colWidths=[logo_w+0.6*cm, 18.0*cm-(logo_w+0.6*cm)]
    )
    header.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("ALIGN",(1,0),(1,0),"RIGHT"),
        ("ALIGN",(1,1),(1,1),"RIGHT"), ("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(-1,-1),0)
    ]))
    story += [header, Spacer(1,6),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,6)]

    # ── Keine „Was heute zählt“-Bullets mehr ────────────────────────────────

    # 4) Artikel-Liste -------------------------------------------------------
    # Darstellung:
    #  Titel (gross/fett)
    #  Quelle (verlinkt), kurzes Datum  → EIN Link (nur an Quelle)
    #  2–4 Sätze Zusammenfassung … (Unternehmen …)
    for art in articles:
        title   = (art.get("title") or "").strip()
        source  = (art.get("source") or "").strip()
        url     = (art.get("url") or art.get("link") or "").strip()
        date    = (art.get("date") or "").strip()
        summary = (art.get("summary") or "").strip()
        companies = art.get("companies") if isinstance(art.get("companies"), list) else []
        comp_suffix = f" ({', '.join(companies)})" if companies else ""

        # Titel
        story.append(Paragraph(title, h_title))

        # Meta-Zeile: Quelle verlinkt + Datum (kurz)
        # Link nur 1x – an der Quelle
        meta_html = f"<link href='{url}' color='#0b5bd3'><u>{source}</u></link>"
        if date:
            # Datum kurz DE
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                date_str = dt.strftime("%d.%m.%y")
            except Exception:
                date_str = date
            meta_html += f" — {date_str}"
        story.append(Paragraph(meta_html, meta_line))

        # Summary + (Unternehmen)
        story.append(Paragraph(summary + comp_suffix, body))

    if not articles:
        story.append(Paragraph("Heute keine relevanten Artikel im betrachteten Zeitraum gefunden.", styles["Normal"]))

    # 5) Footer ---------------------------------------------------------------
    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,4),
              Paragraph("© INVESTORY – Alle Angaben ohne Gewähr.", styles["Normal"])]

    # 6) PDF schreiben --------------------------------------------------------
    doc.build(story)

# --------------------------------------------------------------------------- #
# Pipeline & CLI
# --------------------------------------------------------------------------- #
def run_pdf_pipeline():
    # Daten erzeugen
    report = gen_report_data()
    out_path  = f"/tmp/Daily_Investment_Report_{now_local().strftime('%Y-%m-%d')}.pdf"

    # Logo laden
    if not LOGO_URL:
        raise RuntimeError("LOGO_URL fehlt in den Umgebungsvariablen.")
    logo_data = fetch_bytes(LOGO_URL)

    # PDF bauen
    build_pdf(out_path, logo_data, report)

    # >>> Diese Zeile braucht der GitHub-Workflow
    print(out_path)
    return out_path

if __name__ == "__main__":
    run_pdf_pipeline()
