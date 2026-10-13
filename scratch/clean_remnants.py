import re

with open('web_dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace remnants
replacements = {
    'bg-emerald-950/60': 'bg-emerald-50',
    'bg-emerald-950/40': 'bg-emerald-50',
    'bg-emerald-950/20': 'bg-emerald-50',
    'bg-emerald-950/15': 'bg-emerald-50',
    'bg-emerald-950/10': 'bg-emerald-50',
    'bg-rose-950/40': 'bg-rose-50',
    'bg-rose-950/20': 'bg-rose-50',
    'bg-rose-950/15': 'bg-rose-50',
    'bg-rose-950/10': 'bg-rose-50',
    'bg-amber-950/40': 'bg-amber-50',
    'bg-amber-950/15': 'bg-amber-50',
    'bg-amber-950/10': 'bg-amber-50',
    'bg-sky-950/40': 'bg-sky-50',
    'bg-sky-950/15': 'bg-sky-50',
    'from-slate-950': 'from-slate-50',
    'to-slate-950': 'to-slate-100',
    'shadow-emerald-950/50': 'shadow-sm',
    'text-blue-300': 'text-sky-800',
    'bg-blue-500/20 text-blue-300 border border-blue-500/40': 'bg-blue-50 text-blue-700 border border-blue-200'
}

for k, v in replacements.items():
    text = text.replace(k, v)

with open('web_dashboard/templates/company_detail.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("Remnants cleaned successfully!")
