import json
from pathlib import Path

cfg_path = Path("config/peer_benchmarks.json")
with open(cfg_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. Update SIC_3571 peers with greenblatt_roc
sic_3571_rocs = {
    "AAPL": 3.487,
    "DELL": 0.352,
    "HPQ": 0.428,
    "HPE": 0.194,
    "SMCI": 0.245,
    "WDC": 0.152,
    "STX": 0.218,
    "NTAP": 0.385
}

for p in data["industry_benchmarks"]["SIC_3571"]["peers"]:
    t = p.get("ticker", "").upper()
    if t in sic_3571_rocs:
        p["greenblatt_roc"] = sic_3571_rocs[t]

# 2. Update SIC_3021 peers with greenblatt_roc and missing fields
sic_3021_rocs = {
    "DECK": 2.236,
    "NKE": 0.409,
    "CROX": 1.245,
    "SKX": 0.288,
    "SHOO": 0.363,
    "WWW": 0.280,
    "ONON": 0.603
}

for p in data["industry_benchmarks"]["SIC_3021"]["peers"]:
    t = p.get("ticker", "").upper()
    if t in sic_3021_rocs:
        p["greenblatt_roc"] = sic_3021_rocs[t]
    if t == "WWW":
        p["beta"] = 1.25
        p["total_debt_usd_m"] = 850.0
        p["interest_expense_usd_m"] = 65.0
        p["effective_tax_rate"] = 0.21
        p["market_cap_usd_m"] = 1200.0
        p["traditional_roic"] = 0.085
        p["adjusted_roic"] = 0.082
        p["wacc"] = 0.092
        p["economic_spread"] = -0.010

# Check if ONON exists in SIC_3021, if not add it
has_onon = any(p.get("ticker", "").upper() == "ONON" for p in data["industry_benchmarks"]["SIC_3021"]["peers"])
if not has_onon:
    data["industry_benchmarks"]["SIC_3021"]["peers"].append({
        "ticker": "ONON",
        "company_name": "On Holding AG",
        "is_target": False,
        "period": "LTM (FY2025 Auditado)",
        "revenue_usd_m": 2500.0,
        "total_assets_usd_m": 3200.0,
        "rd_expense_usd_m": 120.0,
        "rd_intensity": 0.048,
        "capex_usd_m": 95.0,
        "total_reinvestment_intensity": 0.067,
        "net_income_usd_m": 280.0,
        "roa": 0.0875,
        "cfo_usd_m": 420.0,
        "cfroa": 0.1312,
        "sga_expense_usd_m": 1150.0,
        "gross_profit_usd_m": 1500.0,
        "cash_usd_m": 500.0,
        "beta": 1.35,
        "total_debt_usd_m": 200.0,
        "interest_expense_usd_m": 15.0,
        "effective_tax_rate": 0.20,
        "market_cap_usd_m": 16500.0,
        "traditional_roic": 0.265,
        "adjusted_roic": 0.218,
        "wacc": 0.095,
        "economic_spread": 0.123,
        "greenblatt_roc": 0.603
    })

with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("config/peer_benchmarks.json updated successfully with greenblatt_roc!")
