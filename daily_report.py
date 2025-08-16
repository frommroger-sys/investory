import os, requests, io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# --- Secrets & Assets (aus GitHub Actions-Umgebung) ---
WP_BASE         = os.environ["INV_WP_BASE"].rstrip("/")
WP_USERNAME     = os.environ["INV_WP_USER"]
WP_APP_PASSWORD = os.environ["INV_WP_APP_PW"]

LOGO_URL        = os.environ["INV_LOGO_URL"]
POPPINS_REG_URL = os.environ["INV_POPPINS_REG_URL"]
POPPINS_BOLD_URL= os.environ["INV_POPPINS_BOLD_URL"]

UA = {"User-Agent":"Investory-Daily-Report/1.0 (+investory.ch)"}

def fetch_bytes(url):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content

def register_poppins():
    open("/tmp/Poppins-Regular.ttf","wb").write(fetch_bytes(POPPINS_REG_URL))
    open("/tmp/Poppins-Bold.ttf","wb").write(fetch_bytes(POPPINS_BOLD_URL))
    pdfmetrics.registerFont(TTFont("Poppins", "/tmp/Poppins-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Poppins-Bold", "/tmp/Poppins-Bold.ttf"))

def build_pdf(out_path, logo_bytes, report):
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "Poppins" if "Poppins" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading = 14

    title_style = ParagraphStyle("TitleRight", parent=styles["Normal"], alignment=2,
        fontName="Poppins-Bold" if "Poppins-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
        fontSize=14, leading=18, textColor=colors.HexColor("#111"))
    meta_style  = ParagraphStyle("Meta", parent=styles["Normal"], alignment=2, fontSize=9.5, textColor=colors.HexColor("#666"))
    h2 = ParagraphStyle("H2", parent=styles["Normal"], fontName=title_style.fontName,
        fontSize=12.2, leading=16, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#0f2a5a"))
    bullet = ParagraphStyle("Bullet", parent=styles["Normal"], leftIndent=10, bulletIndent=0, spaceAfter=3)

    def p_bullet(txt): 
        return Paragraph(f"<bullet>&#8226;</bullet>{txt}", bullet)
    def p_link(txt, url): 
        return Paragraph(f"<bullet>&#8226;</bullet>{txt} "
                         f"<font color='#0b5bd3'><u><link href='{url}'>Quelle</link></u></font>", bullet)

    # Header mit Logo
    img = ImageReader(io.BytesIO(logo_bytes)); iw, ih = img.getSize()
    target_w = 3.2*cm; scale = target_w / iw
    logo = Image(io.BytesIO(logo_bytes), width=iw*scale, height=ih*scale)
    title = Paragraph("Daily Investment Report", title_style)
    stamp = Paragraph(f"Stand: {datetime.now().strftime('%d.%m.%Y, %H:%M')}", meta_style)

    doc = SimpleDocTemplate(out_path, pagesize=A4,
        leftMargin=1.7*cm, rightMargin=1.7*cm, topMargin=1.5*cm, bottomMargin=1.6*cm)
    story = []
    hdr = Table([[logo, title], ["", stamp]], colWidths=[3.8*cm, 18.0*cm-3.8*cm])
    hdr.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ALIGN",(1,0),(1,0),"RIGHT"), ("ALIGN",(1,1),(1,1),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),4)
    ]))
    story += [hdr, Spacer(1,6), HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6), Spacer(1,8)]

    # Inhalte
    story += [Paragraph("Was heute zählt", h2)]
    for s in report.get("headline", [])[:5]: 
        story.append(p_bullet(s))
    story.append(Spacer(1,8))

    def region(title_txt, data):
        story.append(Paragraph(title_txt, h2))
        if data.get("tldr"):   
            story.append(p_bullet("<b>TL;DR:</b> " + "; ".join(data["tldr"])[:400]))
        if data.get("moves"):  
            story.append(p_bullet("<b>Top Moves:</b> " + "; ".join(data["moves"])[:400]))
        for txt,url in data.get("news", [])[:8]: 
            story.append(p_link(f"<b>Unternehmensnews:</b> {txt}", url))
        if data.get("analyst"): 
            story.append(p_bullet("<b>Analysten-Highlights:</b> " + "; ".join(data["analyst"])[:400]))
        if data.get("macro"):   
            story.append(p_bullet("<b>Makro/Branche:</b> " + " ".join(data["macro"])[:400]))
        story.append(Spacer(1,6))

    order = [("1) Schweiz (SIX)","CH"), ("2) Europa ex CH","EU"), ("3) USA","US"), ("4) Asien (JP, TW, HK)","AS")]
    for title_txt, key in order:
        if "regions" in report and key in report["regions"]:
            region(title_txt, report["regions"][key])

    story += [HRFlowable(color=colors.HexColor("#e6e6e6"), thickness=0.6), Spacer(1,4),
              Paragraph("© INVESTORY – Alle Rechte vorbehalten. Keine Haftung für die Richtigkeit der Daten.", styles["Normal"])]
    doc.build(story)

def wp_upload_media(file_path, title=None, alt_text=None):
    fname = os.path.basename(file_path)
    headers = {"Content-Disposition": f'attachment; filename="{fname}"',
               "User-Agent": "Investory-Report-Uploader/1.0"}
    with open(file_path, "rb") as f:
        files = {"file": (fname, f, "application/pdf")}
        r = requests.post(f"{WP_BASE}/wp-json/wp/v2/media",
                          headers=headers, files=files,
                          auth=(WP_USERNAME, WP_APP_PASSWORD), timeout=60)
    r.raise_for_status()
    return r.json().get("source_url")

def run_pdf_pipeline(report_data):
    register_poppins()
    logo_bytes = fetch_bytes(LOGO_URL)
    out_path = f"/tmp/Daily_Investment_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    build_pdf(out_path, logo_bytes, report_data)
    public_url = wp_upload_media(out_path, title=os.path.basename(out_path),
                                 alt_text="Daily Investment Report (Investory)")
    print("PUBLIC_PDF_URL:", public_url)
    return public_url
