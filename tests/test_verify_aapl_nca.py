import json

with open("data/processed/AAPL/financial_statements.json", "r", encoding="utf-8") as f:
    data = json.load(f)

as_rep_bs = data.get("as_reported_statements", {}).get("balance_sheet", [])
print("=== AS-REPORTED BALANCE SHEET ROWS (Non-Current) ===")
for r in as_rep_bs:
    lbl = r.get("label", "")
    concept = r.get("concept", "")
    vals = r.get("values", {})
    if any(k in lbl.lower() or k in concept.lower() for k in ["intangible", "property", "marketable", "other non-current", "total non-current", "total assets"]):
        ltm = vals.get("LTM")
        fy25 = vals.get("FY2025")
        ltm_str = f"${ltm/1e6:,.1f}M" if isinstance(ltm, (int, float)) else str(ltm)
        fy25_str = f"${fy25/1e6:,.1f}M" if isinstance(fy25, (int, float)) else str(fy25)
        print(f"  * {lbl} [{concept}] -> LTM: {ltm_str} ({ltm}) | FY2025: {fy25_str} ({fy25})")

print("\n=== RESOLVED CANONICAL STATEMENTS (balance_sheet) ===")
res_can_bs = data.get("resolved_canonical_statements", {}).get("balance_sheet", {})
keys = [
    "net_ppe",
    "goodwill_and_intangibles",
    "long_term_investments",
    "other_noncurrent_assets",
    "total_noncurrent_assets",
    "total_assets"
]

total_calculated_ltm = 0.0
total_calculated_fy25 = 0.0

for k in keys:
    v = res_can_bs.get(k, {})
    ltm = v.get("LTM")
    fy25 = v.get("FY2025")
    ltm_str = f"${ltm/1e6:,.1f}M" if isinstance(ltm, (int, float)) else str(ltm)
    fy25_str = f"${fy25/1e6:,.1f}M" if isinstance(fy25, (int, float)) else str(fy25)
    print(f"  * {k:30} -> LTM: {ltm_str} | FY2025: {fy25_str}")
    if k in ["net_ppe", "goodwill_and_intangibles", "long_term_investments", "other_noncurrent_assets"]:
        if isinstance(ltm, (int, float)):
            total_calculated_ltm += ltm
        if isinstance(fy25, (int, float)):
            total_calculated_fy25 += fy25

tot_nca_ltm = res_can_bs.get("total_noncurrent_assets", {}).get("LTM", 0.0)
tot_nca_fy25 = res_can_bs.get("total_noncurrent_assets", {}).get("FY2025", 0.0)
diff_ltm = tot_nca_ltm - total_calculated_ltm

print("\n=== AUDITORÍA MATEMÁTICA LTM ===")
print(f"Suma de partidas hijas no corrientes LTM: ${total_calculated_ltm/1e6:,.1f}M ({total_calculated_ltm})")
print(f"Total Non-Current Assets reportado LTM:   ${tot_nca_ltm/1e6:,.1f}M ({tot_nca_ltm})")
print(f"Diferencia LTM: ${diff_ltm/1e6:,.1f}M ({diff_ltm})")
assert abs(diff_ltm) < 1.0, f"Discrepancia detectada en LTM: {diff_ltm}"

print("\n>>> EXCELENTE: COHERENCIA MATEMÁTICA EXACTA AL 100% (0.00 M de diferencia) EN LTM <<<")
