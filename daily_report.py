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

# -------------------------------------------------
# Load assets (fonts + logo) from provided URLs
# -------------------------------------------------

def load_asset(url, name):
    r = requests.get(url)
    r.raise_for_status()
    return io.BytesIO(r.content)

logo_url = os.environ.get("INV_LOGO_URL")
poppins_reg_url = os.environ.get("INV_POPPINS_REG_URL")
poppins_bold_url = os.environ.get("INV_POPPINS_BOLD_URL")

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
        "Die Inhalte (Marktupdates, Unternehmensmeldungen, Analysen) ",
        "werden hier später durch die KI eingefügt.",
    ])
    c.drawText(text)

    c.showPage()
    c.save()

    with open(filename, "wb") as f:
        f.write(buffer.getvalue())
    return filename

# -------------------------------------------------
# Upload PDF to WordPress
# -------------------------------------------------

def wp_upload_media(file_path, title="Daily Report"):
    wp_base = os.environ.get("INV_WP_BASE")
    wp_user = os.environ.get("INV_WP_USER")
    wp_app_pw = os.environ.get("INV_WP_APP_PW")

    if not wp_base or not wp_user or not wp_app_pw:
        raise RuntimeError("WordPress credentials not fully set in environment.")

    url = f"{wp_base}/wp-json/wp/v2/media"
    with open(file_path, "rb") as f:
        headers = {
            "Content-Disposition": f'attachment; filename="{os.path.basename(file_path)}"',
        }
        r = requests.post(url, headers=headers, data=f, auth=(wp_user, wp_app_pw))
        r.raise_for_status()
        data = r.json()
        # FIX: Handle list response from WP REST API
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data.get("source_url")

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
