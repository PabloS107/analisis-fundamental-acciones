# Test Infrastructure Specification: Universal Fundamental Analysis Orchestrator

**Version:** 1.0.0  
**Status:** Active  
**Scope:** Universal Fundamental Analysis Orchestrator E2E Testing Track (Track A)  
**Author:** E2E Test Writer (`teamwork_preview_test_writer_e2e`)  
**Compliance:** Strict adherence to `AGENTS.md` (Reglas 1, 2, 3, 4) & `PROJECT.md`

---

## 1. Executive Summary & Testing Philosophy

The **Universal Fundamental Analysis Orchestrator** automates SEC EDGAR XBRL ingestion, financial statement normalization, multi-archetype fundamental scoring (Piotroski, Mohanram, Novy-Marx, Altman Z'', Greenblatt ROC, WACC/EVA), institutional executive report generation (Word `.docx`, Markdown `.md`, Excel `.xlsx`), and a Django web analytics dashboard across diverse corporate and financial archetypes:
1. `CORPORATE_STANDARD` / `STANDARD_CORPORATE` (e.g. `AAPL`, `DECK`, `NVDA`)
2. `FINANCIAL_BANKING` (e.g. `JPM`, `NU`)
3. `INSURANCE` (e.g. `PGR`)
4. `REAL_ESTATE_REIT` (e.g. `O` / Realty Income)
5. `PLATFORM_ECOSYSTEM` (e.g. `MELI` / MercadoLibre)

The testing infrastructure guarantees **Opaque-Box End-to-End (E2E)** validation, ensuring that:
- Every feature operates dynamically without hardcoded constants or ticker branches (`AGENTS.md` Regla 4).
- Zero regressions occur on benchmark control companies (`AAPL`, `DECK`) (`AGENTS.md` Regla 2).
- Non-applicable corporate models (Altman Z'', Greenblatt ROC) are inhibited on financial/insurance entities with pedagogical transparency (`AGENTS.md` Regla 3).
- Accounting identities, debt hierarchies, and cash flows maintain mathematical rigor (`AGENTS.md` Regla 1 & 2).

---

## 2. 4-Tier Test Architecture

The E2E test suite in `tests/test_e2e_universal_orchestrator.py` follows a rigorous 4-tier testing hierarchy:

```
┌────────────────────────────────────────────────────────────────────────┐
│             Tier 4: Real-World Application Scenarios                  │
│       All 8 Audited Issuers: AAPL, DECK, JPM, MELI, NU, NVDA, O, PGR   │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 3: Cross-Feature & Archetype Interactions             │
│   Pairwise Combinations: Banking vs Corporate, Insurance vs Banking,   │
│   REIT vs Corporate, Platform vs Corporate, Cross-Archetype Pipeline  │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 2: Boundary, Edge & Corner Cases                      │
│   >=5 tests each for R1, R2, R3, R4, R5 (Empty inputs, Zero debt vs    │
│   Debt-free, Negative interest, Extreme ratios, Missing peers)         │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 1: Feature Coverage (Primary Specifications)          │
│   >=5 tests each for R1, R2, R3, R4, R5 (Happy paths & Contracts)      │
└────────────────────────────────────────────────────────────────────────┘
```

### Tier 1: Feature Coverage (`TestTier1FeatureCoverage`)
Covers the core contract and expected behavior for each of the 5 project requirements:
- **R1 (Universal Archetype Detection & Persistence):**
  - SIC code classification: Banking (SIC 60xx/61xx -> `FINANCIAL_BANKING`).
  - SIC code classification: Insurance (SIC 63xx/64xx -> `INSURANCE`).
  - SIC code classification: REITs (SIC 6798 -> `REAL_ESTATE_REIT`).
  - Business model & XBRL signature classification: Platform Ecosystem (hybrid retail + credit -> `PLATFORM_ECOSYSTEM`).
  - Standard Corporate default & reciprocal aliases (`STANDARD_CORPORATE` <-> `CORPORATE_STANDARD`).
  - Schema validation of canonical `archetype` persistence in `financial_statements.json`.
- **R2 (Archetype Decoupling in Central Scoring Engine):**
  - Banking archetype suppresses Altman Z'' and Greenblatt ROC (`is_applicable: False` with pedagogical note).
  - Insurance archetype suppresses Altman Z'' and Greenblatt ROC (`is_applicable: False`).
  - Multi-taxonomic debt hierarchy: reads `canonical_summary.total_debt` and supports IFRS, REIT, Banking GAAP, Insurance GAAP.
  - Zero-debt guard: companies with financial debt are never erroneously classified as `is_debt_free = True`.
  - Valuation model branching: WACC/ROIC for Corporate/REIT vs Ke/ROTCE for Banking/Insurance.
- **R3 (Accounting Normalization & XBRL Taxonomies):**
  - Long-term banking debt tag inclusion (`LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`).
  - P&L sign normalization: COGS, R&D, and SG&A ingested as positive magnitudes.
  - Audit engine identity verification operates cleanly without masking signs (`abs(cogs)`).
  - Commercial real estate acquisitions decoupled from maintenance CapEx in REITs.
  - Free Cash Flow calculation consistency across archetypes.
- **R4 (Eradication of Hardcoded Fallbacks):**
  - Solvency report builder: zero hardcoded Nubank loans ($30,400M), deposits ($36,600M), ROTCE (26.40%), or BACEN texts.
  - Valuation report builder: zero hardcoded Nubank TBV ($7,646.3M) or $1,000.0M revenue fallbacks.
  - ROIC/WACC report builder: zero hardcoded Apple debt ($82,347M) or intangible stock ($79,597M).
  - Earnings report builder: zero hardcoded ticker branches (`elif ticker_clean == "AAPL"` / `"DECK"`).
  - Decoupled insurance reports: PGR uses Combined Ratio, Float, and RBC rather than banking loan/deposit templates.
- **R5 (Web Dashboard Hardening & Multi-Archetype Integration):**
  - Django analytics view data adapters handle all 8 companies without 404 errors.
  - Interactive simulator contract in `company_detail.html` branches by archetype (prevents $0.00 DCF valuation on banks).
  - ROTCE vs ROIC index and table metric alignment (`ROTCE - Ke` vs `ROIC - WACC`).
  - Segment mix denominator calculation strictly excludes items with `is_subtotal == True`.
  - Multi-archetype summary payload integrity across all views.

### Tier 2: Boundary & Corner Cases (`TestTier2BoundaryCornerCases`)
Stresses the system against extreme, degenerate, and adversarial inputs (>=5 tests per requirement):
- **R1 Boundary:** Empty/None metadata, borderline SIC codes, whitespace/mixed-case strings, conflicting signatures, missing financial statements.
- **R2 Boundary:** Genuine debt-free ($0 debt) vs leveraged company, negative interest expense sign guard (normalized via `abs()`, not "debt-free"), negative equity (distressed balance sheet), extreme interest coverage (EBIT/0 or 0/Interest), zero tangible capital denominator.
- **R3 Boundary:** Zero CapEx (pure SaaS), zero COGS (pure services), negative CFO in FCF, extreme acquisition years vs zero-acquisition years in REITs, non-standard fiscal period keys.
- **R4 Boundary:** Unknown ticker with missing peer benchmarks (renders 'N/D' with explanation, never fake numbers), missing market data (Beta/Price = None), all-None solvency metrics, negative earnings/FCF in valuation, unknown ticker in report builders.
- **R5 Boundary:** Unknown ticker URL handling, empty segment lists, zero/negative segment totals, missing `fundamental_scores.json` dynamic calculation fallback, extreme interactive simulator parameters (-100% growth, 0% discount rate).

### Tier 3: Cross-Feature & Archetype Interactions (`TestTier3CrossFeatureArchetypes`)
Validates pairwise cross-archetype consistency and behavioral invariants:
1. **Banking vs Corporate (`JPM`/`NU` vs `AAPL`/`DECK`):** Validates that Banking inhibits corporate metrics while Corporate evaluates them, and debt hierarchies differentiate deposits from borrowings.
2. **Insurance vs Banking (`PGR` vs `JPM`):** Validates that Insurance models underwriting profit (Combined Ratio) and Float, while Banking models Net Interest Margin (NIM) and Loan Portfolio, both suppressing Altman Z''/ROC.
3. **REIT vs Corporate (`O` vs `NVDA`):** Validates that REIT isolates property acquisitions from maintenance CapEx, whereas Corporate treats PPE additions under standard CapEx.
4. **Platform vs Corporate (`MELI` vs `AAPL`):** Validates that Platform handles hybrid balances (merchandise inventory + fintech loans) with strictly positive expense magnitudes.
5. **Universal Pipeline Invariant:** All archetypes produce conforming `canonical_summary` structures with non-negative expense magnitudes and canonical `archetype` keys.

### Tier 4: Real-World Application Scenarios (`TestTier4RealWorldScenarios`)
Validates real processed artifacts from `data/processed/{TICKER}/` across all 8 companies:
1. `AAPL` — Standard Corporate Control Company: 100% zero regressions, valid debt ($84B-$98B), positive P&L, WACC spread.
2. `DECK` — Standard Corporate Control Company: 100% zero regressions, genuine debt-free status ($0 debt), split-adjusted consistency.
3. `JPM` — Universal Banking: Financial Banking archetype, non-zero total debt, corporate metrics inhibited, ROTCE / Ke spread.
4. `MELI` — Platform Ecosystem: Platform archetype, positive COGS/SG&A magnitudes, valid gross margin (44.5%), non-zero debt.
5. `NU` — Digital Banking: Financial Banking archetype, non-zero total debt ($5.7B), corporate metrics inhibited, dynamic reports.
6. `NVDA` — Semiconductor Corporate: Standard Corporate archetype, non-zero debt, Novy-Marx GP/A, R&D intensity.
7. `O` — Realty Income REIT: Real Estate REIT archetype, non-zero debt ($29B), maintenance CapEx decoupled from commercial real estate acquisitions ($4.6B).
8. `PGR` — Progressive Insurance: Insurance archetype, non-zero debt ($8.3B), float and investment assets accounted for, dedicated insurance templates.

---

## 3. Test Environment & Execution

### Prerequisites
- Python 3.10+ (Current runtime: Python 3.14).
- Standard library `unittest` (Zero external test dependencies required).
- Working Directory: Project Root (`c:\Users\pablo\OneDrive\Documents\Analisis fundamental de acciones`).

### Test Commands

#### Run the entire E2E Test Suite:
```powershell
python -m unittest tests/test_e2e_universal_orchestrator.py -v
```

#### Run specific Tiers:
```powershell
# Tier 1: Feature Coverage
python -m unittest tests.test_e2e_universal_orchestrator.TestTier1FeatureCoverage -v

# Tier 2: Boundary & Corner Cases
python -m unittest tests.test_e2e_universal_orchestrator.TestTier2BoundaryCornerCases -v

# Tier 3: Cross-Archetype Interactions
python -m unittest tests.test_e2e_universal_orchestrator.TestTier3CrossFeatureArchetypes -v

# Tier 4: Real-World Scenarios (All 8 Companies)
python -m unittest tests.test_e2e_universal_orchestrator.TestTier4RealWorldScenarios -v
```

#### Run a specific test case:
```powershell
python -m unittest tests.test_e2e_universal_orchestrator.TestTier4RealWorldScenarios.test_t4_01_aapl_control_integrity -v
```

---

## 4. Test Isolation, Determinism & Mocking Strategy

1. **Isolation:** Each test method constructs isolated in-memory fixtures or uses temporary directories (`tempfile.TemporaryDirectory`) that are destroyed during `tearDown()`.
2. **Deterministic Output Derivation:** All expected values are derived from audited SEC EDGAR XBRL filings, authoritative corporate accounts, and published academic formulas (Piotroski 2000, Mohanram 2005, Novy-Marx 2013, Damodaran).
3. **No File System Pollution:** No test writes temporary state to `.agents/teamwork/` or leaves un-tracked files in the workspace.
4. **Zero Hardcoded Hacks:** Test assertions verify dynamic behavior across tickers and archetypes without hardcoding ticker bypasses.
