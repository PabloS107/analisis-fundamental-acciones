import os, sys
ROOT_DIR = r"c:\Users\pablo\OneDrive\Documents\Analisis fundamental de acciones"
sys.path.insert(0, os.path.join(ROOT_DIR, 'web_dashboard'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')
import django; django.setup()
from django.test import Client

client = Client()
response = client.get('/company/DECK/')
print("Status code:", response.status_code)
content = response.content.decode('utf-8')

# 1. Posición de Tab 3 en la barra de navegación
pos_statements = content.find("switchTab('statements')")
pos_segments = content.find("switchTab('segments')")
pos_charts = content.find("switchTab('charts')")
pos_scorecards = content.find("switchTab('scorecards')")
print(f"Positions: statements={pos_statements}, segments={pos_segments}, charts={pos_charts}, scorecards={pos_scorecards}")
assert pos_statements < pos_segments < pos_charts < pos_scorecards, "Tab order wrong"

# 2. Nombre de la pestaña
print("Checking tab title...")
assert 'Rentabilidad &amp; Asignación de Capital' in content or 'Rentabilidad & Asignación de Capital' in content

# 3. Gráfico 1
print("Checking Chart 1 labels...")
assert "label: 'Beneficio Operativo ($M)'" in content, "Missing Beneficio Operativo in content"
assert "label: 'Free Cash Flow ($M)'" in content, "Missing Free Cash Flow in content"
assert "const ebits = " in content, "Missing const ebits in content"
assert "Cascada P&amp;L + Cash Flow" in content, "Missing Cascada P&L badge"

# 4. Context values
print("Checking context values in content...")
assert '1252.9' in content, "1252.9 not in content"
assert '1117.8' in content, "1117.8 not in content"

# 5. Styling: verify tab-charts specifically has zero arbitrary rainbow colors
print("Checking styling in tab-charts...")
start = content.find('id="tab-charts"')
end = content.find('id="tab-segments"')
tab_charts_html = content[start:end]

assert 'text-3xl font-black text-slate-900 mt-1' in tab_charts_html, "Slate 900 big metric not in tab-charts"
assert 'text-purple-700' not in tab_charts_html, "Purple still in tab-charts"
assert 'text-emerald-700' not in tab_charts_html, "Emerald still in tab-charts"
import re
for m in re.finditer(r'.{0,40}text-amber-700.{0,40}', tab_charts_html):
    print("AMBER MATCH:", m.group(0))

assert 'text-amber-700' not in tab_charts_html, "Amber still in tab-charts"
assert 'text-sky-700' not in tab_charts_html, "Sky still in tab-charts"

print("ALL ASSERTIONS PASSED!")
