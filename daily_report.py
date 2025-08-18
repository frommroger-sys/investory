import os
import io
import requests
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

UA = {"User-Agent": "Investory-Daily-Report/1.0 (+investory.ch)"}

# -------------------------------------------------
# Load assets (fonts + logo) from provided URLs
# -------------------------------------------------
def load_asset(url, name):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return io.BytesIO(r.content)

logo_url = os.environ.get("INV_LOGO_URL")
poppins_reg_url = os.environ.get("INV_POPPINS_REG_URL")
poppins_bold_url = os.environ.get("INV_POPPINS_BOLD_URL")

# Diese Zeilen laufen beim Import und laden die Assets
logo_img = ImageReader(load_asset(logo_url, "logo"))
pdfmetrics.registerFont(TTFont("Poppins-Regular", load_asset(poppins_reg_url, "Poppins-Regular")))
pdfmetrics.registerFont(TTFont("Poppins-Bold", load_asset(poppins_bold_url, "Poppins-Bold")))

# -------------------------------------------------
# Generate PDF
# -------------------------------------------------
def generate_pdf(filename="daily_report.pdf"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Logo
    c.drawImage(logo_img, width - 6*cm, height - 3*cm, width=5*cm, preserveAspectRatio=True, mask='auto')

    # Title
    c.setFont("Poppins-Bold", 20)
    c.drawString(2*cm, height - 3*cm, "Investory Daily Report")

    # Date
    c.setFont("Poppins-Regular", 12)
    c.drawString(2*cm, height - 4*cm, datetime.now().strftime("%d.%m.%Y"))

    # Placeholder for content
    text = c.beginText(2*cm, height - 6*cm)
    text.setFont("Poppins-Regular", 12)
    text.textLines([
        "Dies ist ein automatisch generierter Report.",
        "",
        "Die Inhalte (Marktupdates, Unternehmensmeldungen, Analysen)",
        "werden hier später durch die KI eingefügt.",
    ])
    c.drawText(text)

    c.showPage()
    c.save()

    with open(filename, "wb") as f:
        f.write(buffer.getvalue())
    return filename

# -------------------------------------------------
# Upload PDF to WordPress (Multipart!)
# -------------------------------------------------
def wp_upload_media(file_path, title="Daily Report"):
    wp_base = os.environ.get("INV_WP_BASE")
    wp_user = os.environ.get("INV_WP_USER")
    wp_app_pw = os.environ.get("INV_WP_APP_PW")

    if not wp_base or not wp_user or not wp_app_pw:
        raise RuntimeError("WordPress credentials not fully set in environment.")

    url = f"{wp_base.rstrip('/')}/wp-json/wp/v2/media"
    fname = os.path.basename(file_path)

    headers = {"User-Agent": "Investory-Report-Uploader/1.0"}
    data = {}
    if title:
        data["title"] = title

    with open(file_path, "rb") as f:
        files = {
            "file": (fname, f, "application/pdf")  # <-- wichtig: Multipart 'file'
        }
        r = requests.post(
            url,
            headers=headers,
            auth=(wp_user, wp_app_pw),
            files=files,              # <-- statt data=f
            data=data,
            timeout=60,
        )

    # Fehler gut sichtbar machen
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        snippet = (r.text or "")[:300]
        raise RuntimeError(f"WP upload failed {r.status_code}: {snippet}") from e

    # Response robust auslesen
    try:
        resp = r.json()
    except ValueError:
        raise RuntimeError(f"WP returned non-JSON response: {r.status_code}")

    if isinstance(resp, list) and resp:
        resp = resp[0]

    source_url = (
        resp.get("source_url")
        or (resp.get("guid") or {}).get("rendered")
    )
    if not source_url:
        raise RuntimeError(f"No source_url in WP response: {resp}")

    return source_url

# -------------------------------------------------
# Pipeline
# -------------------------------------------------
def run_pdf_pipeline():
    out_path = generate_pdf("daily_report.pdf")
    public_url = wp_upload_media(out_path, title=os.path.basename(out_path))
    print("Report hochgeladen:", public_url)
    return public_url

if __name__ == "__main__":
    run_pdf_pipeline()
