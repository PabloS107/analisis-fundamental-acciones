import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
sys.path.insert(0, os.path.abspath('web_dashboard'))
django.setup()

from django.test import RequestFactory
from analytics.views import company_detail

rf = RequestFactory()

for ticker in ['AAPL', 'DECK', 'NU']:
    resp = company_detail(rf.get(f'/company/{ticker}/'), ticker)
    html = resp.content.decode('utf-8')
    has_b_label = '($B)' in html or 'en $B' in html
    has_m_subtitle = 'Valores en $M USD' in html
    
    # Check that PnL values are formatted with M
    has_m_pnl = '$' in html and 'M' in html
    
    print(f"=== {ticker} ===")
    print(f"Status Code: {resp.status_code}")
    print(f"Has unwanted ($B) label: {has_b_label}")
    print(f"Has 'Valores en $M USD' subtitle: {has_m_subtitle}")
    
    # Search for sample revenue values in HTML
    for line in html.splitlines():
        if 'chartRevNI' in line or 'rev_series' in line or 'Ingresos ($M)' in line:
            print(f"Chart label found: {line.strip()[:100]}")
        if 'Margen de Intereses (NII) ($M)' in line:
            print(f"Banking label found: {line.strip()[:100]}")
        if 'Flujos de Caja: CFO, CapEx &amp; FCF ($M)' in line:
            print(f"Cash flow header found: {line.strip()[:100]}")
