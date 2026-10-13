import re

with open('web_dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    text = f.read()

tokens = re.findall(r'[a-zA-Z0-9_\-\/]+', text)
suspicious = set()
for t in tokens:
    if any(k in t for k in ['950', '850', 'text-blue-300', 'text-sky-300', 'text-slate-300', 'text-amber-300', 'text-purple-300', 'text-rose-300', 'text-emerald-300']):
        suspicious.add(t)

print("Suspicious dark remnants count:", len(suspicious))
for s in sorted(suspicious):
    print(" ", s)
