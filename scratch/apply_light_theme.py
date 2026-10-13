import re

def convert_to_light_theme(html: str) -> str:
    # 1. Backgrounds & Containers
    html = html.replace('bg-slate-900/90', 'bg-white')
    html = html.replace('bg-slate-900/80', 'bg-white')
    html = html.replace('bg-slate-900/50', 'bg-white')
    html = html.replace('bg-slate-900', 'bg-white')
    html = html.replace('bg-slate-950/70', 'bg-slate-50')
    html = html.replace('bg-slate-950/60', 'bg-slate-50')
    html = html.replace('bg-slate-950/50', 'bg-slate-50')
    html = html.replace('bg-slate-950/40', 'bg-slate-50')
    html = html.replace('bg-slate-950/30', 'bg-slate-50')
    html = html.replace('bg-slate-950', 'bg-slate-50')
    html = html.replace('bg-slate-800/80', 'bg-slate-50')
    html = html.replace('bg-slate-800/70', 'bg-slate-50')
    html = html.replace('bg-slate-800/60', 'bg-slate-50')
    html = html.replace('bg-slate-800/50', 'bg-slate-50')
    html = html.replace('bg-slate-800/40', 'bg-slate-50')
    html = html.replace('bg-slate-800/30', 'bg-slate-50')
    html = html.replace('bg-slate-800', 'bg-slate-50')
    html = html.replace('bg-slate-850/80', 'bg-slate-50')
    html = html.replace('bg-slate-850', 'bg-slate-50')

    # 2. Borders
    html = html.replace('border-slate-800/80', 'border-slate-200')
    html = html.replace('border-slate-800/60', 'border-slate-200')
    html = html.replace('border-slate-800/40', 'border-slate-200')
    html = html.replace('border-slate-800', 'border-slate-200')
    html = html.replace('border-slate-700/80', 'border-slate-200')
    html = html.replace('border-slate-700/60', 'border-slate-200')
    html = html.replace('border-slate-700', 'border-slate-200')
    html = html.replace('divide-slate-800', 'divide-slate-100')
    html = html.replace('divide-slate-700', 'divide-slate-100')

    # 3. Typography
    html = html.replace('text-white', 'text-slate-900')
    html = html.replace('text-slate-200', 'text-slate-800')
    html = html.replace('text-slate-300', 'text-slate-700')
    html = html.replace('text-slate-400', 'text-slate-500')
    html = html.replace('hover:text-white', 'hover:text-slate-900')

    # 4. Accents & Badges
    html = html.replace('text-emerald-400', 'text-emerald-700')
    html = html.replace('text-emerald-300', 'text-emerald-700')
    html = html.replace('bg-emerald-500/10', 'bg-emerald-50')
    html = html.replace('bg-emerald-500/20', 'bg-emerald-50')
    html = html.replace('border-emerald-500/20', 'border-emerald-200')
    html = html.replace('border-emerald-500/30', 'border-emerald-200')
    html = html.replace('border-emerald-500/40', 'border-emerald-200')

    html = html.replace('text-sky-400', 'text-sky-700')
    html = html.replace('text-sky-300', 'text-sky-700')
    html = html.replace('bg-sky-500/10', 'bg-sky-50')
    html = html.replace('bg-sky-500/20', 'bg-sky-50')
    html = html.replace('border-sky-500/20', 'border-sky-200')
    html = html.replace('border-sky-500/30', 'border-sky-200')
    html = html.replace('border-sky-500/40', 'border-sky-200')

    html = html.replace('text-purple-400', 'text-purple-700')
    html = html.replace('text-purple-300', 'text-purple-700')
    html = html.replace('bg-purple-500/10', 'bg-purple-50')
    html = html.replace('bg-purple-500/20', 'bg-purple-50')
    html = html.replace('border-purple-500/20', 'border-purple-200')
    html = html.replace('border-purple-500/30', 'border-purple-200')
    html = html.replace('border-purple-500/40', 'border-purple-200')

    html = html.replace('text-rose-400', 'text-rose-700')
    html = html.replace('text-rose-300', 'text-rose-700')
    html = html.replace('bg-rose-500/10', 'bg-rose-50')
    html = html.replace('bg-rose-500/20', 'bg-rose-50')
    html = html.replace('border-rose-500/20', 'border-rose-200')
    html = html.replace('border-rose-500/30', 'border-rose-200')
    html = html.replace('border-rose-500/40', 'border-rose-200')

    html = html.replace('text-amber-400', 'text-amber-700')
    html = html.replace('text-amber-300', 'text-amber-700')
    html = html.replace('bg-amber-500/10', 'bg-amber-50')
    html = html.replace('bg-amber-500/20', 'bg-amber-50')
    html = html.replace('border-amber-500/20', 'border-amber-200')
    html = html.replace('border-amber-500/30', 'border-amber-200')
    html = html.replace('border-amber-500/40', 'border-amber-200')

    # 5. Table rows and search input
    html = html.replace('hover:bg-slate-800', 'hover:bg-slate-50')
    html = html.replace('hover:bg-slate-700', 'hover:bg-slate-100')
    html = html.replace('placeholder-slate-500', 'placeholder-slate-400')

    # 6. Chart.js Grid and Ticks
    html = html.replace("grid: { color: 'rgba(51, 65, 85, 0.4)' }", "grid: { color: 'rgba(226, 232, 240, 0.8)' }")
    html = html.replace("ticks: { color: '#94a3b8'", "ticks: { color: '#64748b'")
    html = html.replace("legend: { labels: { color: '#e2e8f0'", "legend: { labels: { color: '#334155'")
    html = html.replace("borderColor: '#0f172a'", "borderColor: '#ffffff'")

    return html

with open('web_dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    orig = f.read()

new_html = convert_to_light_theme(orig)

# Save backup and update
with open('web_dashboard/templates/company_detail.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

print("company_detail.html successfully updated to Institutional Clean Light Theme!")
