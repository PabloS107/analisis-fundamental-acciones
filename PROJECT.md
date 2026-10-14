# Project: Universal Fundamental Analysis Orchestrator Audit & Refactoring

## Architecture
The Universal Fundamental Analysis Orchestrator processes corporate, financial, insurance, and real estate issuers from official SEC EDGAR XBRL filings into executive institutional reports (Word .docx and Markdown .md) and a Django web dashboard.

```
                    [SEC EDGAR XBRL Filings (10-K / 10-Q)]
                                      │
                                      ▼
                        [pipeline/sec_extractor.py]
                    - Detect archetype (SIC + XBRL)
                    - Canonical persistence (financial_statements.json)
                    - P&L normalization (positive magnitudes)
                    - CapEx vs Real Estate acquisition decoupling
                    - Multi-taxonomic debt tag extraction
                                      │
                                      ▼
                   [pipeline/financial_scoring_engine.py]
                    - Read archetype & branch scoring engines
                    - Inhibit corporate ROC/Altman on Financials & Insurance
                    - Canonical debt extraction (IFRS, REIT, GAAP, Bank)
                    - Interest expense sign guards & WACC/Ke branching
                    - Output: fundamental_scores.json
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
      [Report Builders & Pipeline]                [web_dashboard/]
 - solvency_report_builder.py              - company_detail.html (JS sim)
 - valuation_report_builder.py             - index.html (ROTCE vs ROIC)
 - roic_wacc_report_builder.py             - views.py (no 404, segment mix)
 - generate_earnings_report.py
 (Zero hardcoded constants, tri-modal)
                 │                                         │
                 ▼                                         ▼
          Audited DOCX, MD                          Live Web Dashboard
```

## Feature Inventory
Every feature identified during the Survey phase mapped to its assigned milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Universal Archetype Detection | Classify and persist `archetype` in `financial_statements.json` using SIC codes (6300-6499 for Insurance) and financial signatures with reciprocal aliases (`CORPORATE_STANDARD` / `STANDARD_CORPORATE`) without ticker hardcoding. | M1 | Survey (Explorer 1) |
| 2 | JPM Long-Term Debt Tag Extraction | Include `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities` in banking taxonomy to extract audited ~$500.000M total debt. | M1 | Survey (Explorer 1) |
| 3 | MELI P&L Sign Normalization | Ingest COGS, R&D, and SG&A with positive magnitudes at extraction; remove `abs(cogs)` masks in `audit_engine.py` and fix DIO/divergence calculations. | M1 | Survey (Explorer 1) |
| 4 | Realty Income (O) CapEx Decoupling | Decouple `PaymentsToAcquireCommercialRealEstate` from routine maintenance CapEx, resolving FCF audit failures across all periods. | M1 | Survey (Explorer 1) |
| 5 | Archetype Ingestion in Scoring Engine | In `financial_scoring_engine.py`, read `archetype` from `financial_statements.json` and persist in `scoring_results`. | M2 | Survey (Explorer 2) |
| 6 | Inhibit Corporate Metrics on Banks/Insurers | Suppress Altman Z'' and Greenblatt ROC calculations for `FINANCIAL_BANKING` and `INSURANCE`, returning `is_applicable: False` with pedagogical notes per AGENTS.md Regla 3. | M2 | Survey (Explorer 2) |
| 7 | Multi-Taxonomic Total Debt Hierarchy | Fallback to `canonical_summary.total_debt` and support IFRS (`ifrs-full_Borrowings`), REITs (`NotesPayable`), Banking GAAP, and Insurance GAAP in `extract_period_metrics`. | M2 | Survey (Explorer 2) |
| 8 | Interest Expense Sign Guard & WACC Branching | Normalize interest expense with `abs()`, prevent false 4.5% estimation, and branch WACC/ROIC vs Ke/ROTCE by archetype. | M2 | Survey (Explorer 2) |
| 9 | Eradicate Hardcoded Fallbacks in Solvency Builder | Eliminate $30,400 M loans, $36,600 M deposits, 26.40% ROTCE, 10.8% NIM, $9,185.7 M cash, BACEN narrative from `solvency_report_builder.py`. | M3 | Survey (Explorer 3) |
| 10 | Eradicate Hardcoded Fallbacks in Valuation Builder | Eliminate $7,646.3 M TBV, 1.60 TBV/share, 26.4% base, 1000.0 M revenue, Nubank Latin America narratives from `valuation_report_builder.py`. | M3 | Survey (Explorer 3) |
| 11 | Eradicate Hardcoded Fallbacks in ROIC/WACC Builder | Eliminate Apple debt ($82,347 M), intangible stock ($79,597 M), market cap ($4,901,082 M) fallbacks from `roic_wacc_report_builder.py`. | M3 | Survey (Explorer 3) |
| 12 | Decouple Insurance from Banking Reports | Separate Insurance (`INSURANCE`) report builder from Banking (`FINANCIAL_BANKING`) so PGR uses Combined Ratio, Float, RBC, and P/BV instead of banking loan/deposit templates. | M3 | Survey (Explorer 3) |
| 13 | Eliminate Ticker Branches in Earnings Report | Eradicate `elif ticker_clean == "AAPL"` / `DECK` text blocks in `generate_earnings_report.py`, deriving segment analysis dynamically. | M3 | Survey (Explorer 3) |
| 14 | Fix Interactive JS Simulator in Web Dashboard | Branch simulator in `company_detail.html` by archetype to prevent DCF calculation from evaluating to $0.00 on banks/insurers. | M4 | Survey (Explorer 3) |
| 15 | Fix ROTCE vs ROIC Labels and Spreads | Synchronize `ROTCE - Ke` vs `ROIC - WACC` labels and formulas in `index.html`, `company_detail.html`, and `views.py`. | M4 | Survey (Explorer 3) |
| 16 | Eradicate 404 Errors for JPM, O, PGR | Ensure `fundamental_scores.json` exists or is computed dynamically in `web_dashboard/analytics/views.py`. | M4 | Survey (Explorer 3) |
| 17 | Fix Segment Mix Denominator | Exclude items with `is_subtotal == True` from segment mix denominators in `views.py` and `company_detail.html`. | M4 | Survey (Explorer 3) |
| 18 | Triangulated Verification & Zero Regressions | Pass 100% of 4-tier E2E tests, zero regressions on control companies (AAPL, DECK), inspect DOCX, Django Web Dashboard, Markdown, and clean forensic audit. | M5 | Survey (All) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Archetype Detection & XBRL Taxonomies | Features 1, 2, 3, 4 (`pipeline/sec_extractor.py`, `pipeline/audit_engine.py`) | None | DONE |
| M2 | Financial Scoring Engine Decoupling | Features 5, 6, 7, 8 (`pipeline/financial_scoring_engine.py`) | M1 | DONE |

| M3 | Eradication of Hardcoded Fallbacks | Features 9, 10, 11, 12, 13 (`solvency_report_builder.py`, `valuation_report_builder.py`, `roic_wacc_report_builder.py`, `generate_earnings_report.py`) | M1, M2 | DONE |
| M4 | Web Dashboard Hardening & Sync | Features 14, 15, 16, 17 (`web_dashboard/templates/`, `web_dashboard/analytics/views.py`) | M2, M3 | IN_PROGRESS |
| M5 | Final Triangulated Verification & Victory Gate | Feature 18 (Full E2E suite pass, AAPL/DECK control, artifact inspection, forensic audit) | M1, M2, M3, M4, E2E | PLANNED |

## Interface Contracts
### `pipeline/sec_extractor.py` ↔ `pipeline/financial_scoring_engine.py`
- Contract: `financial_statements.json` must contain a top-level `"archetype"` key: `str` with values in `["CORPORATE_STANDARD", "STANDARD_CORPORATE", "FINANCIAL_BANKING", "INSURANCE", "REAL_ESTATE_REIT", "PLATFORM_ECOSYSTEM"]`.
- `canonical_summary.total_debt`: `dict` mapping period strings (`"FY2025"`, `"LTM"`, etc.) to `float` representing total financial debt in base currency.
- `canonical_summary.cost_of_goods_sold`: `dict` mapping period strings to positive `float` values.
- `canonical_summary.capital_expenditures`: `dict` mapping period strings to positive `float` representing maintenance/capital additions, excluding real estate investment acquisitions.

### `pipeline/financial_scoring_engine.py` ↔ Report Builders & `web_dashboard/`
- Contract: `fundamental_scores.json` must contain:
  - `"archetype"`: `str`
  - `"scoring_results"`: `dict`
  - `"debt_and_solvency_analysis"`:
    - `"latest_result"` -> `"distress_models"` -> `"altman_zone"`: `"NO APLICABLE"` for `FINANCIAL_BANKING` and `INSURANCE`.
  - `"greenblatt_roc_analysis"`:
    - `"is_applicable"`: `False`, `"rating"`: `"NO APLICABLE"` for `FINANCIAL_BANKING` and `INSURANCE`.
  - `"wacc_analysis"`:
    - `"model_type"`: `"WACC"` for corporate/REIT, `"COST_OF_EQUITY_KE"` for banking/insurance.
    - `"spread"`: `ROIC - WACC` or `ROTCE - Ke`.

## Code Layout
- `pipeline/sec_extractor.py`: SEC EDGAR XBRL extractor and canonical statements builder.
- `pipeline/audit_engine.py`: Financial statements identity verification and audit engine.
- `pipeline/financial_scoring_engine.py`: Universal scoring, debt solvency, Altman Z'', Greenblatt ROC, and WACC.
- `pipeline/solvency_report_builder.py`: Solvency report builder (corporate, banking, insurance).
- `pipeline/valuation_report_builder.py`: Valuation report builder (DCF, Excess Return, P/BV vs ROE).
- `pipeline/roic_wacc_report_builder.py`: ROIC & WACC report builder.
- `pipeline/generate_earnings_report.py`: Master document builder (Word .docx, Markdown .md).
- `web_dashboard/analytics/views.py`: Django views and data adapters.
- `web_dashboard/templates/analytics/company_detail.html`: Detail view template with interactive simulator.
- `web_dashboard/templates/analytics/index.html`: Dashboard overview template.
- `tests/`: Automated unit and integration test suite.
