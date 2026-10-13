import os, sys, django
sys.path.insert(0, os.path.abspath('web_dashboard'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
django.setup()
from django.test import RequestFactory
from analytics.views import company_detail

req = RequestFactory().get('/company/AAPL/')
resp = company_detail(req, ticker='AAPL')
html = resp.content.decode('utf-8')

print("--- P&L Table & Card Samples (AAPL) ---")
for line in html.splitlines():
    if '$' in line and 'M' in line and any(c.isdigit() for c in line):
        print(line.strip()[:100])

print("\n--- Javascript Chart Datasets / Ticks (AAPL) ---")
for line in html.splitlines():
    if any(k in line for k in ['revs =', 'nis =', 'cfos =', 'fcf =', 'capex =', 'toLocaleString']):
        print(line.strip()[:120])
