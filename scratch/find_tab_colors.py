import re

with open('web_dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

cur_tab = 'header'
for i, line in enumerate(lines[:2400]):
    if 'id="tab-' in line:
        cur_tab = line.strip()
    for col in ['text-purple-700', 'text-amber-700', 'text-sky-700']:
        if col in line:
            print(f"{i+1} [{cur_tab[:25]}]: {line.strip()[:100]}")
