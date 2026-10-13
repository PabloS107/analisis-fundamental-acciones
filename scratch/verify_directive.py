import os, sys, django
sys.path.insert(0, os.path.abspath('web_dashboard'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
django.setup()
from django.test import RequestFactory
from analytics.views import company_detail

for ticker in ['AAPL', 'DECK', 'MELI', 'NU']:
    req = RequestFactory().get(f'/company/{ticker}/')
    resp = company_detail(req, ticker=ticker)
    assert resp.status_code == 200, f'Failed {ticker}'
    html = resp.content.decode('utf-8')
    assert 'fmtThousands' in html, f'fmtThousands missing in {ticker}'
    assert 'fmtUSD_M' in html, f'fmtUSD_M missing in {ticker}'
    assert 'credit_portfolio_bn' not in html, f'credit_portfolio_bn found in {ticker}'
    assert '($B)' not in html, f'($B) found in {ticker}'
    
    # Check that in chartRevNI we use fmtThousands and fmtUSD_M
    assert "callback: v => '$' + fmtThousands(v) + 'M'" in html
    assert "label: ctx => ctx.dataset.label + ': ' + fmtUSD_M(ctx.parsed.y, 1)" in html
    
    # Check that numbers are formatted with comma
    if ticker == 'AAPL':
        assert '$416,161.0M' in html or '$391,035.0M' in html or '$99,803.0M' in html
    elif ticker == 'MELI':
        assert 'GMV Trimestral' in html
        assert '$21,900M' in html
        assert '$16,400.0M' in html  # credit portfolio in millions

    print(f"=== {ticker}: VERIFIED SUCCESSFULLY ===")

print("\nALL ARCHETYPES VERIFIED AND IN PERFECT HARMONY!")
