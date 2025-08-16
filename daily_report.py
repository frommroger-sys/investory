import os
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# ----------------------------------------------------
# PDF erstellen
# ----------------------------------------------------
def create_pdf(output_path: str):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    # Beispiel-Inhalt
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, height - 2 * cm, "Investory Daily Report")

    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, height - 3 * cm, "Dies ist ein automatisch generierter Report.")

    c.showPage()
    c.save()

# ----------------------------------------------------
# Upload zu WordPress
# ----------------------------------------------------
def wp_upload_media(file_path: str, title: str = "Daily Report"):
    wp_base = os.environ.get("INV_WP_BASE")
    wp_user = os.environ.get("INV_WP_USER")
    wp_app_pw = os.environ.get("INV_WP_APP_PW")

    if not wp_base or not wp_user or not wp_app_pw:
        raise ValueError("Fehlende WordPress-Umgebungsvariablen (INV_WP_BASE, INV_WP_USER, INV_WP_APP_PW).")

    url = f"{wp_base}/wp-json/wp/v2/media"
    with open(file_path, "rb") as f:
        headers = {
            "Content-Disposition": f'attachment; filename="{os.path.basename(file_path)}"',
        }
        r = requests.post(
            url,
            headers=headers,
            auth=(wp_user, wp_app_pw),
            files={"file": f},
        )

    r.raise_for_status()
    data = r.json()

    # ✅ Hier der Fix: Falls WordPress eine Liste zurückgibt, erstes Element nehmen
    if isinstance(data, list) and len(data) > 0:
        data = data[0]

    return data.get("source_url")

# ----------------------------------------------------
# Pipeline
# ----------------------------------------------------
def run_pdf_pipeline():
    out_path = "daily_report.pdf"
    create_pdf(out_path)

    public_url = wp_upload_media(out_path, title=os.path.basename(out_path))
    print(f"✅ Report hochgeladen: {public_url}")
    return public_url

# ----------------------------------------------------
# Main
# ----------------------------------------------------
if __name__ == "__main__":
    try:
        run_pdf_pipeline()
    except Exception as e:
        print("PIPELINE ERROR:", str(e))
        raise
