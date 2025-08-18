#!/usr/bin/env python3
# coding: utf-8
"""
Investory – Daily Investment Report
Erzeugt werktags gegen 06:00 Europe/Zurich einen PDF-Marktüberblick
und lädt ihn in die WordPress-Mediathek hoch.
"""
import os, io, json, random, string, requests
from datetime import datetime
from typing import Dict
import pytz                                     # ← NEU
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
#  Konstanten & Helfer
# --------------------------------------------------------------------------- #
UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}
TZ = pytz.timezone("Europe/Zurich")            # ← NEU

def now_local() -> datetime:
    """Aktuelle Zeit in Europe/Zurich"""
    return datetime.now(TZ)

def debug(msg: str):
    print(f"[INVESTORY] {msg}")


# ---------------------- ENV / Secrets -------------------------------------- #
WP_BASE         = (os.environ.get("INV_WP_BASE") or "").rstrip("/")
WP_USER         = os.environ.get("INV_WP_USER")
WP_APP_PASSWORD = os.environ.get("INV_WP_APP_PW")

LOGO_URL        = os.environ.get("INV_LOGO_URL")
POPPINS_REG_URL = os.environ.get("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL= os.environ.get("INV_POPPINS_BOLD_URL")

OAI_KEY         = os.environ.get("INV_OAI_API_KEY")      # OpenAI API-Key


# ---------------------- Helpers -------------------------------------------- #
def fetch_bytes(url: str) -> bytes:
    if not url:
        raise ValueError("Asset-URL ist leer.")
    debug(f"GET asset: {url}")
    r = requests.get(url, headers=UA, timeout=60)
    debug(f" -> {r.status_code}, {len(r.content)} bytes")
    r.raise_for_status()
    return r.content


def register_poppins() -> bool:
    """Poppins-Schrift laden & registrieren (fällt auf Helvetica zurück)"""
    try:
        open("/tmp/Poppins-Regular.ttf", "wb").write(fetch_bytes(POPPINS_REG_URL))
        open("/tmp/Poppins-Bold.ttf",    "wb").write(fetch_bytes(POPPINS_BOLD_URL))
        pdfmetrics.registerFont(TTFont("Poppins",       "/tmp/Poppins-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins-Bold",  "/tmp/Poppins-Bold.ttf"))
        debug("Poppins registered ✓")
        return True
    except Exception as e:
        debug(f"Poppins fallback (Helvetica). Reason: {e}")
        return False


# ---------------------- OpenAI --------------------------------------------- #
def gen_report_data_via_openai() -> Dict:
    """Fragt OpenAI nach strukturierten Markt-Daten (JSON)"""
    if not OAI_KEY:
        debug("OpenAI key missing → using fallback content.")
        return {
            "headline": ["(Fallback) Märkte stabil, Anleger warten auf neue Impulse."],
            "regions": {k: {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]} 
                        for k in ("CH","EU","US","AS")}
        }

    prompt = f"""
Du bist ein erfahrener Finanzredakteur. Erstelle einen kompakten Investment-Überblick (DE).
Datum: {now_local().strftime('%Y-%m-%d')}
Gib ausschließlich JSON wie folgt zurück:
{{
  "headline": ["..."],
  "regions": {{
    "CH": {{"tldr":[],"moves":[],"news":[["Kurztext","https://..."]],"analyst":[],"macro":[]}},
    "EU": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}},
    "US": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}},
    "AS": {{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}}
  }}
}}
Regeln: 2–5 Headlines; nur Plausibles; Links nur wenn plausibel, sonst 'news' leer.
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
        "max_tokens": 1200
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
        debug(f"OpenAI response not JSON. Fallback. Reason: {e}")
        parsed = {"headline": ["(OpenAI-Fehler) Marktüberblick nicht verfügbar."],
                  "regions": {k: {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}
                              for k in ("CH","EU","US","AS")}}

    # Defaults
    parsed.setdefault("headline", [])
    parsed.setdefault("regions", {})
    for k in ("CH","EU","US","AS"):
        parsed["regions"].setdefault(k, {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]})
    return parsed


# ---------------------- PDF Builder ---------------------------------------- #
def build_pdf(out_path: str, logo_bytes: bytes, report: dict):
    debug(f"PDF → {out_path}")
    poppins_ok = register_poppins()

    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "Poppins" if poppins_ok else "Helvetica"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading  = 14

    title_style = ParagraphStyle("TitleRight", parent=styles["Normal"],
                                 alignment=2,
                                 fontName="Poppins-Bold" if poppins_ok else "Helvetica-Bold",
                                 fontSize=14.5, leading=18, textColor=colors.HexColor("#111"))
    meta_style  = ParagraphStyle("Meta", parent=styles["Normal"],
                                 alignment=2, fontSize=9.5,
                                 textColor=colors.HexColor("#666"))
    h2   = ParagraphStyle("H2", parent=styles["Normal"],
                          fontName=title_style.fontName,
                          fontSize=12.2, leading=16,
                          spaceBefore=6, spaceAfter=3,
                          textColor=colors.HexColor("#0f2a5a"))
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"],
                            leftIndent=10, bulletIndent=0, spaceAfter=3)

    def p_bullet(txt: str): return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)
    def p_link(txt: str, url: str):
        return Paragraph(
            f"<bullet>&#8226;</bullet>{txt} "
            f"<font color='#0b5bd3'><u><link href='{url}'>Quelle</link></u></font>",
            bullet
        )

    # Header
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    scale = (3.2 * cm) / iw
    logo  = Image(io.BytesIO(logo_bytes), width=iw * scale, height=ih * scale)
    title = Paragraph("Daily Investment Report", title_style)
    stamp = Paragraph(f"Stand: {now_local().strftime('%d.%m.%Y, %H:%M')}", meta_style)

    doc   = SimpleDocTemplate(out_path, pagesize=A4,
                              leftMargin=1.7*cm, rightMargin=1.7*cm,
                              topMargin=1.5*cm, bottomMargin=1.6*cm)

    story = []
    hdr   = Table([[logo, title], ["", stamp]],
                  colWidths=[3.8*cm, 18.0*cm - 3.8*cm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN",  (1,0), (1,0), "RIGHT"),
        ("ALIGN",  (1,1), (1,1), "RIGHT"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]))
    story += [hdr, Spacer(1,6),
              HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,8)]

    # Inhalte
    story += [Paragraph("Was heute zählt", h2)]
    for s in report.get("headline", [])[:5]:
        story.append(p_bullet(s))
    story.append(Spacer(1,8))

    def region(title_txt: str, data: dict):
        story.append(Paragraph(title_txt, h2))
        if data.get("tldr"):
            story.append(p_bullet("<b>TL;DR:</b> " + "; ".join(data["tldr"])[:400]))
        if data.get("moves"):
            story.append(p_bullet("<b>Top Moves:</b> " + "; ".join(data["moves"])[:400]))
        for item in (data.get("news") or [])[:8]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                txt, url = item
                story.append(p_link(f"<b>Unternehmensnews:</b> {txt}", url))
        if data.get("analyst"):
            story.append(p_bullet("<b>Analysten-Highlights:</b> "
                                  + "; ".join(data["analyst"])[:400]))
        if data.get("macro"):
            story.append(p_bullet("<b>Makro/Branche:</b> "
                                  + " ".join(data["macro"])[:400]))
        story.append(Spacer(1,6))

    for title_txt, key in [("1) Schweiz (SIX)", "CH"),
                           ("2) Europa ex CH",  "EU"),
                           ("3) USA",           "US"),
                           ("4) Asien (JP, TW, HK)", "AS")]:
        if key in report.get("regions", {}):
            region(title_txt, report["regions"][key])

    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6),
              Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. "
                        "Keine Haftung für die Richtigkeit der Daten.",
                        styles["Normal"])]

    doc.build(story)
    debug(f"PDF saved ({os.path.getsize(out_path)} bytes)")


# ---------------------- WP-Upload (Redirect-sicher) ------------------------- #
def _upload_once(file_path: str, filename_override: str = None,
                 endpoint_variant: int = 1):
    """
    Läd die Datei hoch, ohne Redirects automatisch zu folgen,
    damit der Authorization-Header erhalten bleibt.
    endpoint_variant:
      1 = /wp-json/wp/v2/media
      2 = /index.php?rest_route=/wp/v2/media   (Rewrite-Bypass)
    """
    url = (f"{WP_BASE}/wp-json/wp/v2/media" if endpoint_variant == 1
           else f"{WP_BASE}/index.php?rest_route=/wp/v2/media")

    fname = filename_override or os.path.basename(file_path)

    headers = {
        "User-Agent":      "Investory-Report-Uploader/1.0",
        "Accept":          "application/json",
        "Content-Disposition": f'attachment; filename="{fname}"'
    }

    debug(f"Upload → {url} as {fname} (variant={endpoint_variant})")
    with open(file_path, "rb") as f:
        files = {"file": (fname, f, "application/pdf")}
        r = requests.post(url, headers=headers, files=files,
                          auth=(WP_USER, WP_APP_PASSWORD),
                          timeout=60, allow_redirects=False)

    debug(f"Upload status: {r.status_code}")
    if r.status_code in (301, 302, 307, 308):
        redir = r.headers.get("Location")
        debug(f"Redirect {r.status_code} → {redir}")
        # Erneuter Versuch inkl. Auth-Header
        with open(file_path, "rb") as f:
            r = requests.post(redir, headers=headers, files=files,
                              auth=(WP_USER, WP_APP_PASSWORD),
                              timeout=60, allow_redirects=False)
        debug(f"2nd attempt status: {r.status_code}")

    body = {}
    try:
        body = r.json()
    except ValueError:
        body = {"raw": (r.text or "")[:400]}

    return r.status_code, body


def wp_upload_media(file_path: str) -> str:
    """Robuster Upload mit Fallback-Strategie & Validierung"""
    st, body = _upload_once(file_path, endpoint_variant=1)

    if st != 201:
        debug("Retry on alt endpoint (index.php?rest_route=/wp/v2/media)")
        st, body = _upload_once(file_path, endpoint_variant=2)

    if st != 201:
        unique = ("Daily_Investment_Report_"
                  + now_local().strftime('%Y-%m-%d_%H%M%S')
                  + "_" + ''.join(random.choices(string.ascii_lowercase+string.digits, k=6))
                  + ".pdf")
        debug(f"Retry with unique name: {unique}")
        st, body = _upload_once(file_path, filename_override=unique, endpoint_variant=1)
        if st != 201:
            st, body = _upload_once(file_path, filename_override=unique, endpoint_variant=2)

    # Quelle extrahieren
    source_url = None
    if isinstance(body, dict):
        source_url = (body.get("source_url")
                      or (body.get("guid") or {}).get("rendered"))

    if not source_url:
        raise RuntimeError(f"No valid source_url found. Body: {body}")

    debug(f"API source_url: {source_url}")
    return source_url


# ---------------------- Pipeline ------------------------------------------- #
def run_pdf_pipeline() -> str:
    """Gesamter Ablauf: Daten → PDF → Upload"""
    report_data = gen_report_data_via_openai()

    out_path  = f"/tmp/Daily_Investment_Report_{now_local().strftime('%Y-%m-%d')}.pdf"
    logo_bytes = fetch_bytes(LOGO_URL)
    build_pdf(out_path, logo_bytes, report_data)

    public_url = wp_upload_media(out_path)
    print("PUBLIC_PDF_URL:", public_url)
    print("LOCAL_PDF_PATH:", out_path)
    return public_url


# ---------------------- CLI-Entry-Point ------------------------------------ #
if __name__ == "__main__":
    run_pdf_pipeline()
