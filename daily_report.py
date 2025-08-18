import os, io, json, requests, random, string
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}

# --- ENV / Secrets ---
WP_BASE         = (os.environ.get("INV_WP_BASE") or "").rstrip("/")
WP_USER         = os.environ.get("INV_WP_USER")
WP_APP_PASSWORD = os.environ.get("INV_WP_APP_PW")

LOGO_URL        = os.environ.get("INV_LOGO_URL")
POPPINS_REG_URL = os.environ.get("INV_POPPINS_REG_URL")
POPPINS_BOLD_URL= os.environ.get("INV_POPPINS_BOLD_URL")

OAI_KEY         = os.environ.get("INV_OAI_API_KEY")  # OpenAI API Key

def debug(msg: str):
    print(f"[INVESTORY] {msg}")

# ---------------------- Helpers ----------------------
def fetch_bytes(url: str) -> bytes:
    if not url:
        raise ValueError("Asset-URL ist leer.")
    debug(f"GET asset: {url}")
    r = requests.get(url, headers=UA, timeout=60)
    debug(f" -> {r.status_code}, {len(r.content)} bytes")
    r.raise_for_status()
    return r.content

def register_poppins() -> bool:
    ok = True
    try:
        open("/tmp/Poppins-Regular.ttf","wb").write(fetch_bytes(POPPINS_REG_URL))
        open("/tmp/Poppins-Bold.ttf","wb").write(fetch_bytes(POPPINS_BOLD_URL))
        pdfmetrics.registerFont(TTFont("Poppins", "/tmp/Poppins-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins-Bold", "/tmp/Poppins-Bold.ttf"))
        debug("Poppins registered ✓")
    except Exception as e:
        ok = False
        debug(f"Poppins fallback (Helvetica). Reason: {e}")
    return ok

# ---------------------- OpenAI -----------------------
def gen_report_data_via_openai() -> dict:
    if not OAI_KEY:
        debug("OpenAI key missing → using fallback content.")
        return {
            "headline": ["(Fallback) Märkte stabil, Anleger warten auf neue Impulse."],
            "regions": {
                "CH": {"tldr":["SIX seitwärts."], "moves":[], "news":[], "analyst":[], "macro":[]},
                "EU": {"tldr":["Europa leicht fester."], "moves":[], "news":[], "analyst":[], "macro":[]},
                "US": {"tldr":["US-Futures gemischt."], "moves":[], "news":[], "analyst":[], "macro":[]},
                "AS": {"tldr":["Asien uneinheitlich."], "moves":[], "news":[], "analyst":[], "macro":[]},
            }
        }

    prompt = f"""
Du bist ein erfahrener Finanzredakteur. Erstelle einen kompakten Investment-Überblick (DE).
Datum: {datetime.now().strftime('%Y-%m-%d')}
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
            {"role": "user", "content": prompt}
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
        parsed = {
            "headline": ["(OpenAI-Fehler) Kompakter Marktüberblick nicht verfügbar."],
            "regions": {"CH":{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]},
                        "EU":{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]},
                        "US":{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]},
                        "AS":{"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]}}
        }
    parsed.setdefault("headline", [])
    parsed.setdefault("regions", {})
    for k in ("CH","EU","US","AS"):
        parsed["regions"].setdefault(k, {"tldr":[],"moves":[],"news":[],"analyst":[],"macro":[]})
    return parsed

# ---------------------- PDF Builder ------------------
def build_pdf(out_path: str, logo_bytes: bytes, report: dict):
    debug(f"PDF → {out_path}")
    poppins_ok = register_poppins()

    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "Poppins" if poppins_ok else "Helvetica"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading = 14

    title_style = ParagraphStyle(
        "TitleRight", parent=styles["Normal"], alignment=2,
        fontName="Poppins-Bold" if poppins_ok else "Helvetica-Bold",
        fontSize=14.5, leading=18, textColor=colors.HexColor("#111")
    )
    meta_style  = ParagraphStyle("Meta", parent=styles["Normal"], alignment=2, fontSize=9.5, textColor=colors.HexColor("#666"))
    h2 = ParagraphStyle("H2", parent=styles["Normal"], fontName=title_style.fontName,
                        fontSize=12.2, leading=16, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#0f2a5a"))
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"], leftIndent=10, bulletIndent=0, spaceAfter=3)

    def p_bullet(txt: str): return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)
    def p_link(txt: str, url: str):
        return Paragraph(f"<bullet>&#8226;</bullet>{txt} "
                         f"<font color='#0b5bd3'><u><link href='{url}'>Quelle</link></u></font>", bullet)

    # Header
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    target_w = 3.2*cm; scale = target_w / iw
    logo = Image(io.BytesIO(logo_bytes), width=iw*scale, height=ih*scale)
    title = Paragraph("Daily Investment Report", title_style)
    stamp = Paragraph(f"Stand: {datetime.now().strftime('%d.%m.%Y, %H:%M')}", meta_style)

    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=1.7*cm, rightMargin=1.7*cm, topMargin=1.5*cm, bottomMargin=1.6*cm)
    story = []
    hdr = Table([[logo, title], ["", stamp]], colWidths=[3.8*cm, 18.0*cm-3.8*cm])
    hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("ALIGN",(1,0),(1,0),"RIGHT"), ("ALIGN",(1,1),(1,1),"RIGHT"),
                             ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
                             ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story += [hdr, Spacer(1,6), HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6), Spacer(1,8)]

    # Inhalte
    story += [Paragraph("Was heute zählt", h2)]
    for s in report.get("headline", [])[:5]:
        story.append(p_bullet(s))
    story.append(Spacer(1,8))

    def region(title_txt: str, data: dict):
        story.append(Paragraph(title_txt, h2))
        if data.get("tldr"):   story.append(p_bullet("<b>TL;DR:</b> " + "; ".join(data["tldr"])[:400]))
        if data.get("moves"):  story.append(p_bullet("<b>Top Moves:</b> " + "; ".join(data["moves"])[:400]))
        for item in (data.get("news") or [])[:8]:
            try:
                txt, url = item
                story.append(p_link(f"<b>Unternehmensnews:</b> {txt}", url))
            except Exception:
                continue
        if data.get("analyst"): story.append(p_bullet("<b>Analysten-Highlights:</b> " + "; ".join(data["analyst"])[:400]))
        if data.get("macro"):   story.append(p_bullet("<b>Makro/Branche:</b> " + " ".join(data["macro"])[:400]))
        story.append(Spacer(1,6))

    order = [("1) Schweiz (SIX)","CH"), ("2) Europa ex CH","EU"), ("3) USA","US"), ("4) Asien (JP, TW, HK)","AS")]
    for title_txt, key in order:
        if key in report.get("regions", {}):
            region(title_txt, report["regions"][key])

    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6), Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. Keine Haftung für die Richtigkeit der Daten.", styles["Normal"])]
    doc.build(story)
    try:
        size = os.path.getsize(out_path)
        debug(f"PDF saved ({size} bytes)")
    except Exception:
        pass

# ---------------------- WP Helpers -------------------
def wp_get_media_latest(n=5):
    url = f"{WP_BASE}/wp-json/wp/v2/media?per_page={n}&orderby=date&order=desc"
    r = requests.get(url, auth=(WP_USER, WP_APP_PASSWORD), headers=UA, timeout=60)
    return r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text

def wp_search_media_by_filename(fname: str):
    url = f"{WP_BASE}/wp-json/wp/v2/media?search={fname}"
    r = requests.get(url, auth=(WP_USER, WP_APP_PASSWORD), headers=UA, timeout=60)
    return r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text

# ---------------------- Upload (robust + redirects) --
def _upload_once(file_path: str, filename_override: str = None, endpoint_variant: int = 1):
    """
    endpoint_variant:
      1 = /wp-json/wp/v2/media
      2 = /index.php?rest_route=/wp/v2/media  (Bypass nginx/rewrites)
    """
    if endpoint_variant == 1:
        url = f"{WP_BASE}/wp-json/wp/v2/media"
    else:
        url = f"{WP_BASE}/index.php?rest_route=/wp/v2/media"

    orig_fname = os.path.basename(file_path)
    fname = filename_override or orig_fname

    headers = {
        "User-Agent": "Investory-Report-Uploader/1.0",
        "Accept": "application/json",
        # Content-Disposition ist optional; Requests setzt Boundary & Multipart korrekt.
        "Content-Disposition": f'attachment; filename="{fname}"'
    }

    debug(f"Upload → {url} as {fname} (variant={endpoint_variant})")
    with open(file_path, "rb") as f:
        files = {"file": (fname, f, "application/pdf")}
        r = requests.post(
            url,
            headers=headers,
            files=files,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=60,
            allow_redirects=True,   # << Redirects jetzt erlaubt
        )

    debug(f"Upload status: {r.status_code}")
    if getattr(r, "history", None):
        debug("Redirect history:")
        for h in r.history:
            debug(f" - {h.status_code} → {h.headers.get('Location')}")

    body = None
    try:
        body = r.json()
    except ValueError:
        body = {"raw": (r.text or "")[:400]}

    return r.status_code, body

def wp_upload_media(file_path: str) -> str:
    # 1) normaler Endpoint, Originalname
    st, body = _upload_once(file_path, endpoint_variant=1)

    # 2) falls nicht 201 → alternativer Endpoint (index.php?rest_route=…)
    if st != 201:
        debug("Retry on alt endpoint (index.php?rest_route=/wp/v2/media)")
        st, body = _upload_once(file_path, endpoint_variant=2)

    # 3) falls immer noch nicht 201 → eindeutiger Name probieren (beide Endpoints)
    if st != 201:
        unique = f"Daily_Investment_Report_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{''.join(random.choices(string.ascii_lowercase+string.digits, k=6))}.pdf"
        debug(f"Retry with unique name on main endpoint: {unique}")
        st, body = _upload_once(file_path, filename_override=unique, endpoint_variant=1)
        if st != 201:
            debug("Retry with unique name on alt endpoint.")
            st, body = _upload_once(file_path, filename_override=unique, endpoint_variant=2)

    # --- Ergebnis interpretieren ---
    if isinstance(body, list) and body:
        body = body[0]

    source_url = None
    if isinstance(body, dict):
        source_url = body.get("source_url") or (body.get("guid") or {}).get("rendered")
        debug(f"API source_url: {source_url}")
        if body.get("raw"):
            debug(f"API raw snippet: {body['raw'][:200]}")

    # Wenn die API wieder Mumpitz liefert → verifizieren/finden
    if not source_url:
        debug("No source_url in API response → verify via list/search")
        st2, latest = wp_get_media_latest(5)
        if isinstance(latest, list) and latest:
            debug("Latest media:")
            for it in latest:
                debug(f" - {it.get('id')} : {(it.get('guid') or {}).get('rendered')}")
            # nimm ersten PDF-Eintrag aus 'latest'
            for it in latest:
                guid = (it.get('guid') or {}).get('rendered') or ""
                if guid.lower().endswith(".pdf"):
                    source_url = guid
                    break

        if not source_url:
            st3, found = wp_search_media_by_filename("Daily_Investment_Report_")
            if isinstance(found, list) and found:
                corrected = (found[0].get("guid") or {}).get("rendered")
                debug(f"Search match guid: {corrected}")
                source_url = corrected

    if not source_url:
        raise RuntimeError(f"No valid source_url found. Body: {body}")

    return source_url

# ---------------------- Pipeline ---------------------
def run_pdf_pipeline():
    # 1) Inhalte holen
    report_data = gen_report_data_via_openai()

    # 2) PDF bauen
    out_path = f"/tmp/Daily_Investment_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    logo_bytes = fetch_bytes(LOGO_URL)
    build_pdf(out_path, logo_bytes, report_data)
    try:
        size = os.path.getsize(out_path)
        debug(f"PDF on disk: {out_path} ({size} bytes)")
    except Exception:
        pass

    # 3) Upload (robust, mit Redirect-Handling und Alt-Route)
    public_url = wp_upload_media(out_path)
    print("PUBLIC_PDF_URL:", public_url)
    print("LOCAL_PDF_PATH:", out_path)
    return public_url

if __name__ == "__main__":
    run_pdf_pipeline()
