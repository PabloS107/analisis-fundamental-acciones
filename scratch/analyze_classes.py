import re
from collections import Counter

with open('web_dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    text = f.read()

classes = re.findall(r'class="([^"]+)"', text)
all_tokens = []
for c in classes:
    all_tokens.extend(c.split())

counts = Counter(all_tokens)
for token, count in counts.most_common(60):
    if any(k in token for k in ['slate', 'white', 'gray', 'emerald', 'sky', 'rose', 'purple', 'amber', 'blue']):
        print(f'{token}: {count}')
