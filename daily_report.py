name: Investory Daily Report (Diag)

on:
  workflow_dispatch: {}   # Nur manuell, bis alles läuft
  # schedule:
  #   - cron: "0 4 * * 1-5"   # 06:00 Europe/Zurich ~ 04:00 UTC (Sommerzeit)

jobs:
  run:
    runs-on: ubuntu-latest

    env:
      INV_WP_BASE:           ${{ secrets.INV_WP_BASE }}
      INV_WP_USER:           ${{ secrets.INV_WP_USER }}
      INV_WP_APP_PW:         ${{ secrets.INV_WP_APP_PW }}
      INV_LOGO_URL:          ${{ secrets.INV_LOGO_URL }}
      INV_POPPINS_REG_URL:   ${{ secrets.INV_POPPINS_REG_URL }}
      INV_POPPINS_BOLD_URL:  ${{ secrets.INV_POPPINS_BOLD_URL }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Show repo tree (debug)
        run: |
          pwd
          ls -la
          python -V

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests reportlab

      - name: Diagnostics (assets + WP auth)
        run: |
          python - <<'PY'
          import os, sys, requests, base64, json, traceback

          def say(k,v): print(f"{k}: {v}")
          def head(url):
              try:
                  r = requests.get(url, timeout=20)
                  print(f"GET {url} -> {r.status_code} {len(r.content)} bytes")
                  return r.status_code, r.content
              except Exception as e:
                  print(f"GET {url} ERROR:", e)
                  return None, None

          # 1) Env present (NUR Namen, KEINE Werte)
          for key in ["INV_WP_BASE","INV_WP_USER","INV_WP_APP_PW","INV_LOGO_URL","INV_POPPINS_REG_URL","INV_POPPINS_BOLD_URL"]:
              print(f"ENV {key} set? ", "YES" if os.getenv(key) else "NO")

          # 2) Assets erreichbar?
          for key in ["INV_LOGO_URL","INV_POPPINS_REG_URL","INV_POPPINS_BOLD_URL"]:
              url = os.getenv(key)
              if not url:
                  print(f"{key} MISSING"); continue
              head(url)

          # 3) WordPress API + Auth testen
          base = os.getenv("INV_WP_BASE","").rstrip("/")
          user = os.getenv("INV_WP_USER")
          pw   = os.getenv("INV_WP_APP_PW")
          if base and user and pw:
              api_root = f"{base}/wp-json"
              status,_ = head(api_root)
              media = f"{base}/wp-json/wp/v2/media"
              try:
                  r = requests.get(media, auth=(user,pw), timeout=20)
                  print(f"AUTH GET {media} -> {r.status_code}")
                  # 401/403 deuten auf Auth-/Rechte-Problem
                  if r.status_code not in (200, 201):
                      print("AUTH RESPONSE SNIPPET:", r.text[:300])
              except Exception as e:
                  print("AUTH TEST ERROR:", e)
          else:
              print("WP VARS MISSING: base/user/pw")

          PY

      - name: Generate & upload PDF (pipeline)
        run: |
          python - <<'PY'
          import traceback
          try:
              import daily_report
              report_data = {
                "headline": ["Diagnoselauf – PDF sollte in WP erscheinen"],
                "regions": {}
              }
              url = daily_report.run_pdf_pipeline(report_data)
              print("RESULT_URL:", url)
          except Exception as e:
              print("PIPELINE ERROR:", e)
              traceback.print_exc()
              raise
          PY
