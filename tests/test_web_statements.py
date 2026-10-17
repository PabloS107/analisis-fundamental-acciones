import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'web_dashboard'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_dashboard.settings')

import django
django.setup()

from django.test import Client

from analytics.views import resolve_canonical_capital_flows, resolve_canonical_balance_sheet
import json
import html

class TestStatementsWebDashboard(unittest.TestCase):
    def setUp(self):
        self.client = Client()

    def test_aapl_financial_statements_tab(self):
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Verify active tab is Estados Financieros
        self.assertIn('id="tab-statements"', content)
        self.assertIn('switchTab(\'statements\')', content)
        
        # Verify 3 Statements tables are present
        self.assertIn('Estado de Resultados Consolidado (Income Statement)', content)
        self.assertIn('Estado de Flujos de Caja Consolidado (Cash Flow Statement)', content)
        self.assertIn('Balance General Consolidado (Balance Sheet)', content)

        # Verify 10-year column presence (e.g., FY2018, FY2019, FY2020)
        self.assertIn('FY2018', content)
        self.assertIn('FY2020', content)

        # Verify explicit % (LTM) headers in Column 3
        self.assertIn('% s/ Ventas (LTM)', content)
        self.assertIn('% s/ Ben. Neto (LTM)', content)
        self.assertIn('% s/ Activos (LTM)', content)
        self.assertIn('border-r-2 border-slate-300', content)

        # Verify Income Statement exact rows
        self.assertIn('INGRESOS TOTALES (Total Revenues)', content)
        self.assertIn('Costo de Ventas (Cost of Sales / COGS)', content)
        self.assertIn('UTILIDAD BRUTA (Gross Profit)', content)
        self.assertIn('TOTAL GASTOS OPERATIVOS (Total OpEx)', content)
        self.assertIn('Total Gastos de Venta, Generales y Admin (SG&amp;A Consolidado)', content)
        self.assertIn('EBITDA (Resultado Operativo de Caja / Antes de D&amp;A)', content)
        self.assertIn('Depreciación y Amortización (D&amp;A)', content)
        self.assertIn('RESULTADO OPERATIVO (Operating Profit / EBIT)', content)
        self.assertIn('RESULTADO ANTES DE IMPUESTOS (EBT)', content)
        self.assertIn('UTILIDAD NETA CONSOLIDADA (Consolidated Net Income)', content)
        self.assertIn('Acciones Ponderadas Diluidas en Circulación (Weighted Shares)', content)
        self.assertIn('GANANCIA POR ACCIÓN (EPS Diluido Normalizado)', content)

        # Verify Cash Flow pedagogical buyback reconciliation rows (Opción A)
        self.assertIn('Recompras de acciones en mercado abierto (Open Market)', content)
        self.assertIn('Retención fiscal por liquidación de acciones (SBC Tax Settlement)', content)
        self.assertIn('TOTAL RECOMPRAS DE ACCIONES (Buybacks Consolidados)', content)

        # Verify AAPL FY24 mathematical exactness ($100,390M Fiscal.ai alignment)
        self.assertIn('-$94,949.0M', content)
        self.assertIn('-$5,441.0M', content)
        self.assertIn('-$100,390.0M', content)

        # Verify AAPL Net Debt change sign is negative (-$9,958.0M for FY2024 debt repayments)
        self.assertIn('-$9,958.0M', content)

        # Verify AAPL Net Debt branch in Balance Sheet
        self.assertIn('DEUDA NETA FINANCIERA (NET DEBT)', content)
        self.assertIn('Deuda Neta Financiera', content)
        self.assertNotIn('CAJA NETA EX-DEUDA (NET CASH)', content)

        # Verify SSOT consistency: open-market buybacks summary over closed fiscal years
        self.assertIn('$683,476.0M', content)

    def test_nvda_financial_statements_and_capital_flows(self):
        response = self.client.get('/company/NVDA/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Verify Cash Flow buyback reconciliation rows
        self.assertIn('TOTAL RECOMPRAS DE ACCIONES (Buybacks Consolidados)', content)
        self.assertIn('Adquisiciones netas (M&amp;A)', content)
        self.assertIn('Dividendos pagados en efectivo', content)

        # Verify NVDA dividend captures reported LTM ($974.0M) and FY2026 ($974.0M)
        self.assertIn('-$974.0M', content)

        # Verify NVDA M&A in LTM is -$1,156.0M and FY25 is -$1,007.0M
        self.assertIn('-$1,156.0M', content)
        self.assertIn('-$1,007.0M', content)

        # Verify NVDA Net Buybacks is -$54,526.0M
        self.assertIn('-$54,526.0M', content)

    def test_deck_financial_statements_tab(self):
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('id="tab-statements"', content)
        self.assertIn('INGRESOS TOTALES (Total Revenues)', content)
        self.assertIn('UTILIDAD BRUTA (Gross Profit)', content)
        self.assertIn('EBITDA (Resultado Operativo de Caja / Antes de D&amp;A)', content)
        self.assertIn('FLUJO DE CAJA LIBRE (FCF)', content)
        self.assertIn('ACTIVOS TOTALES', content)
        self.assertIn('PATRIMONIO NETO (EQUITY)', content)

        # Verify DECK Buybacks in FY24 (Open: -$414.9M, Tax: -$10.0M, Total: -$424.9M)
        self.assertIn('-$414.9M', content)
        self.assertIn('-$10.0M', content)
        self.assertIn('-$424.9M', content)

        # Verify DECK Net Cash branch (Cash > Debt -> CAJA NETA EX-DEUDA)
        self.assertIn('CAJA NETA EX-DEUDA (NET CASH)', content)
        self.assertIn('Caja Neta Pura', content)
        self.assertNotIn('DEUDA NETA FINANCIERA (NET DEBT)', content)

    def test_nu_financial_statements_and_capital_flows(self):
        response = self.client.get('/company/NU/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Verify NU M&A captures acquisition ($5.6M in FY2024)
        self.assertIn('-$5.6M', content)

        # Verify NU Net Debt change is positive in LTM / FY24 due to debt issuance
        self.assertIn('$729.2M', content)

    def test_meli_financial_statements_and_capital_flows(self):
        response = self.client.get('/company/MELI/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Verify Cash Flow buyback reconciliation and capital flow rows
        self.assertIn('TOTAL RECOMPRAS DE ACCIONES (Buybacks Consolidados)', content)
        self.assertIn('Adquisiciones netas (M&amp;A)', content)
        self.assertIn('Variación neta de deuda financiera', content)

        # Verify MELI debt flows are properly captured (FY24 +$2,011.0M, FY25 +$2,962.0M)
        self.assertIn('$2,011.0M', content)
        self.assertIn('$2,962.0M', content)

        # Verify MELI acquisitions in FY24 (-$6.0M)
        self.assertIn('-$6.0M', content)

    def test_capital_flows_ssot_math_identities(self):
        # Triangulated math test on all 5 active tickers
        for ticker in ['AAPL', 'NVDA', 'DECK', 'NU', 'MELI']:
            json_path = os.path.join(ROOT_DIR, 'data', 'processed', ticker, 'financial_statements.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                fs = json.load(f)

            periods = fs.get('fiscal_years', [])
            flows = resolve_canonical_capital_flows(fs, periods)

            for p in periods:
                open_mkt = flows['share_repurchases_open_market'][p]
                sbc_tax = flows['share_repurchases_sbc_tax'][p]
                total_bb = flows['share_repurchases_total'][p]
                dr = flows['debt_repayments'][p]
                di = flows['debt_issuances'][p]
                net_debt = flows['net_debt_change'][p]

                # Identity 1: Total Buybacks = Open Market + SBC Tax
                self.assertAlmostEqual(total_bb, open_mkt + sbc_tax, places=2,
                                       msg=f"Discrepancy in {ticker} {p} buybacks")

                # Identity 2: Net Debt Change = Debt Issuances - Debt Repayments
                self.assertAlmostEqual(net_debt, di - dr, places=2,
                                       msg=f"Discrepancy in {ticker} {p} net debt change")

                # Identity 3: All magnitudes are non-negative
                self.assertGreaterEqual(open_mkt, 0.0)
                self.assertGreaterEqual(sbc_tax, 0.0)
                self.assertGreaterEqual(flows['dividends_paid'][p], 0.0)
                self.assertGreaterEqual(flows['acquisitions_ma'][p], 0.0)
                self.assertGreaterEqual(dr, 0.0)
                self.assertGreaterEqual(di, 0.0)

    def test_classified_balance_sheet_structure(self):
        # 1. Test HTML rendering for standard corporations
        for ticker in ['AAPL', 'NVDA', 'DECK', 'MELI']:
            response = self.client.get(f'/company/{ticker}/')
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8')

            # Verify 6 section headers
            self.assertIn('1. ACTIVOS CORRIENTES (CURRENT ASSETS)', content)
            self.assertIn('Efectivo y Equivalentes de Efectivo', content)
            self.assertIn('Inversiones a Corto Plazo / Valores Negociables', content)
            self.assertIn('TOTAL ACTIVOS CORRIENTES', content)

            self.assertIn('2. ACTIVOS NO CORRIENTES (NON-CURRENT ASSETS)', content)
            self.assertIn('Propiedad, Planta y Equipo (PP&amp;E Neto)', content)
            self.assertIn('TOTAL ACTIVOS NO CORRIENTES', content)
            self.assertIn('ACTIVOS TOTALES (TOTAL ASSETS)', content)

            self.assertIn('3. PASIVOS CORRIENTES (CURRENT LIABILITIES)', content)
            self.assertIn('Cuentas por Pagar Comerciales (Proveedores)', content)
            self.assertIn('TOTAL PASIVOS CORRIENTES', content)

            self.assertIn('4. PASIVOS NO CORRIENTES (NON-CURRENT LIABILITIES)', content)
            self.assertIn('TOTAL PASIVOS NO CORRIENTES', content)
            self.assertIn('TOTAL PASIVOS (TOTAL LIABILITIES)', content)

            self.assertIn('5. PATRIMONIO NETO', content)
            self.assertIn('TOTAL PATRIMONIO NETO (EQUITY)', content)

            self.assertIn('6. TOTAL PASIVO Y PATRIMONIO NETO &amp; DIAGNÓSTICO', content)
            self.assertIn('TOTAL PASIVO Y PATRIMONIO NETO', content)
            self.assertIn('CAPITAL DE TRABAJO NETO (FONDO DE MANIOBRA / NWC)', content)

        # 2. Test mathematical identities across periods
        for ticker in ['AAPL', 'NVDA', 'DECK', 'MELI', 'META']:
            json_path = os.path.join(ROOT_DIR, 'data', 'processed', ticker, 'financial_statements.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                fs = json.load(f)
            periods = fs.get('fiscal_years', [])[:4]
            bs = resolve_canonical_balance_sheet(fs, periods)

            for p in periods:
                ca = bs['total_current_assets'][p]
                nca = bs['total_noncurrent_assets'][p]
                ta = bs['total_assets'][p]
                cl = bs['total_current_liabilities'][p]
                ncl = bs['total_noncurrent_liabilities'][p]
                tl = bs['total_liabilities'][p]
                eq = bs['stockholders_equity'][p]
                tle = bs['total_liab_and_equity'][p]
                nwc = bs['net_working_capital'][p]

                # Identity 1: Current Assets + Non-Current Assets == Total Assets
                self.assertAlmostEqual(ca + nca, ta, delta=1.0,
                                       msg=f"{ticker} {p} Assets identity failed")

                # Identity 2: Current Liabilities + Non-Current Liabilities == Total Liabilities
                self.assertAlmostEqual(cl + ncl, tl, delta=1.0,
                                       msg=f"{ticker} {p} Liabilities identity failed")

                # Identity 3: Total Liabilities + Equity == Total Liabilities & Equity == Total Assets (Partida Doble)
                self.assertAlmostEqual(tl + eq, tle, delta=1.0,
                                       msg=f"{ticker} {p} Liab+Equity identity failed")
                self.assertAlmostEqual(tle, ta, delta=1.0,
                                       msg=f"{ticker} {p} Partida Doble identity failed")

                # Identity 4: Net Working Capital == Current Assets - Current Liabilities
                self.assertAlmostEqual(nwc, ca - cl, delta=1.0,
                                       msg=f"{ticker} {p} NWC identity failed")

        # 3. AAPL FY2024 specific audit
        response = self.client.get('/company/AAPL/')
        content = response.content.decode('utf-8')
        self.assertIn('$29,943.0M', content)   # Cash & equivalents
        self.assertIn('$35,228.0M', content)   # Short-term investments
        self.assertIn('$152,987.0M', content)  # Total current assets
        self.assertIn('$176,392.0M', content)  # Total current liabilities
        self.assertIn('-$23,405.0M', content)  # Net Working Capital (Negative working capital)

    def test_meta_balance_sheet_noncurrent_assets(self):
        """Verifica que el Balance General de META en Django y SSOT refleje con exactitud los valores auditados de Fiscal.ai y SEC EDGAR."""
        response = self.client.get('/company/META/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Activos Corrientes LTM
        self.assertIn('$15,462.0M', content)   # Cash
        self.assertIn('$74,798.0M', content)   # Short-term investments
        self.assertIn('$21,752.0M', content)   # Accounts receivable
        self.assertIn('$13,463.0M', content)   # Other current assets
        self.assertIn('$125,475.0M', content)  # Total current assets

        # 2. Activos No Corrientes LTM (Sin sobreestimaciones de 473B o 261B)
        self.assertIn('$225,724.0M', content)  # PP&E Neto
        self.assertIn('$23,985.0M', content)   # ROU Asset (Fiscal.ai suma PP&E + ROU = $249,709M)
        self.assertIn('$23,406.0M', content)   # Goodwill & Intangibles
        self.assertNotIn('$473,362.0M', content)  # Error anterior erradicado
        self.assertIn('$30,157.0M', content)   # Inversiones a LP
        self.assertIn('$261,221.0M', content)  # Total Patrimonio Neto (Equity) auditado
        self.assertIn('$21,209.0M', content)   # Otros activos LP
        self.assertIn('$324,481.0M', content)  # Total activos no corrientes
        self.assertIn('$449,956.0M', content)  # Total Activos

        # 3. Deuda Financiera (Sin falsa deuda a corto plazo)
        self.assertIn('$83,664.0M', content)   # Deuda a largo plazo

    def test_meta_segments_and_geography(self):
        """Verifica que META presente segmentos primarios (FoA, Reality Labs) y desglose jerárquico (Advertising, Other revenue)."""
        response = self.client.get('/company/META/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Segmentos Primarios y Subsegmentos en Tabla
        self.assertIn('Family of Apps', content)
        self.assertIn('Reality Labs', content)
        self.assertIn('Advertising', content)
        self.assertIn('Other revenue', content)

        # 2. Regiones Geográficas primarias y subregión
        self.assertIn('United States &amp; Canada', content)
        self.assertIn('Europe', content)
        self.assertIn('Asia-Pacific', content)
        self.assertIn('Rest of World', content)
        self.assertIn('United States', content)

        # 3. Gráficos solo contienen los segmentos primarios
        import re
        m_p = re.search(r'const prodLabels = (\[.*?\]);', content)
        m_g = re.search(r'const geoLabels = (\[.*?\]);', content)
        self.assertIsNotNone(m_p)
        self.assertIsNotNone(m_g)
        self.assertEqual(json.loads(m_p.group(1)), ["Family of Apps", "Reality Labs"])
        self.assertEqual(json.loads(m_g.group(1)), ["United States & Canada", "Europe", "Asia-Pacific", "Rest of World"])

    def test_deck_segments_reconciliation_and_styling(self):
        """Verifica que DECK tenga Segmentos como Tab 2, cuadre con $5,527.3M LTM, paleta neutral y leyendas legibles."""
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Tab 2 es Segmentos & Geografía (inmediatamente después de Statements y antes de Charts)
        pos_statements = content.find("switchTab('statements')")
        pos_segments = content.find("switchTab('segments')")
        pos_charts = content.find("switchTab('charts')")
        pos_quality = content.find("switchTab('quality')")
        self.assertTrue(pos_statements < pos_segments < pos_charts < pos_quality,
                        "El orden de pestañas debe ser: 1. Statements, 2. Segments, 3. Charts, 4. Quality")

        # 2. Total Neto Consolidado en tablas con valor $5,527.3M y 100.0%
        self.assertIn('(=) Total Neto Consolidado', content)
        self.assertIn('$5,527.3M', content)
        self.assertIn('100.0%', content)

        # 3. Valores LTM de marcas conciliados exactamente con $5,527.3M
        self.assertIn('$2,724.4M', content)  # UGG LTM
        self.assertIn('$2,658.7M', content)  # HOKA LTM
        self.assertIn('$144.2M', content)    # Other Brands LTM
        self.assertIn('$3,174.9M', content)  # Domestic LTM
        self.assertIn('$2,352.4M', content)  # International LTM

        # 4. Tarjetas resumen con color fijo neutro (slate) y sin colores dispersos o engañosos
        self.assertIn('text-slate-800 bg-slate-100', content)
        self.assertNotIn('text-emerald-700">{{ kpis_segments.intl_ltm }}', content)
        self.assertNotIn('text-violet-700 bg-violet-50', content)

        # 5. Leyendas de gráficos Donut con contraste oscuro '#334155' y negrita
        self.assertIn("labels: { color: '#334155', font: { size: 11, weight: '600' }", content)

    def test_aapl_segments_reconciliation_and_styling(self):
        """Verifica que AAPL (empresa de control) tenga Segmentos como Tab 2 y mantenga cuadre exacto."""
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Tab order
        pos_statements = content.find("switchTab('statements')")
        pos_segments = content.find("switchTab('segments')")
        pos_charts = content.find("switchTab('charts')")
        pos_quality = content.find("switchTab('quality')")
        self.assertTrue(pos_statements < pos_segments < pos_charts < pos_quality)

        # 2. Total Neto Consolidado
        self.assertIn('(=) Total Neto Consolidado', content)
        self.assertIn('$466,823M', content)

        # 3. Tarjetas con color fijo neutro slate
        self.assertIn('text-slate-800 bg-slate-100', content)

    def test_deck_charts_tab_position_series_and_styling(self):
        """Verifica que el Tab 3 sea Rentabilidad & Asignación de Capital con 5 series y estilo slate unificado."""
        response = self.client.get('/company/DECK/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Posición de Tab 3 en la barra de navegación y orden consolidado de 6 pestañas
        pos_statements = content.find("switchTab('statements')")
        pos_segments = content.find("switchTab('segments')")
        pos_charts = content.find("switchTab('charts')")
        pos_quality = content.find("switchTab('quality')")
        pos_forensic = content.find("switchTab('forensic')")
        pos_reversedcf = content.find("switchTab('reversedcf')")
        self.assertTrue(pos_statements < pos_segments < pos_charts < pos_quality < pos_forensic < pos_reversedcf,
                        f"Orden de pestañas incorrecto: statements={pos_statements}, segments={pos_segments}, charts={pos_charts}, quality={pos_quality}, forensic={pos_forensic}, reversedcf={pos_reversedcf}")

        # 2. Nombre de la pestaña
        self.assertIn('Rentabilidad & Asignación de Capital', content)

        # 3. Gráfico 1 incluye Beneficio Operativo y FCF junto a Ingresos, Bruto y Neto
        self.assertIn("label: 'Beneficio Operativo ($M)'", content)
        self.assertIn("label: 'Free Cash Flow ($M)'", content)
        self.assertIn("const ebits = ", content)
        self.assertIn("Cascada P&amp;L + Cash Flow", content)

        # 4. Verificación de valores de EBIT y FCF en el HTML (LTM DECK)
        self.assertIn('1252.9', content)  # EBIT LTM DECK: $1,252.9M
        self.assertIn('1117.8', content)  # FCF LTM DECK: $1,117.8M

        # 5. Tarjetas de Capital Allocation Framework y badges en estilo slate unificado dentro de tab-charts
        start_charts = content.find('id="tab-charts"')
        end_charts = content.find('id="tab-segments"')
        tab_charts_html = content[start_charts:end_charts]

        self.assertIn('text-3xl font-black text-slate-900 mt-1', tab_charts_html)
        self.assertNotIn('text-purple-700', tab_charts_html)
        self.assertNotIn('text-emerald-700', tab_charts_html)
        self.assertNotIn('text-amber-700', tab_charts_html)
        self.assertNotIn('text-sky-700', tab_charts_html)

    def test_consolidated_quality_and_forensic_tabs_and_grounded_tooltips(self):
        """Verifica que las pestañas 4 (Calidad de Negocio) y 5 (Auditoría Forense) integren tooltips grounded con fórmulas reales."""
        response = self.client.get('/company/AAPL/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # 1. Pestaña 4: Calidad de Negocio & Retornos sobre Capital presente y con selector interactivo de modelos
        self.assertIn('id="tab-quality"', content)
        self.assertIn('id="btn-model-fscore"', content)
        self.assertIn('id="btn-model-gscore"', content)
        self.assertIn('id="model-fscore-panel"', content)
        self.assertIn('id="model-gscore-panel"', content)

        # 2. Tooltips grounded con fórmulas y valores en Pestaña 4
        self.assertIn('Piotroski F-Score (0-9)', content)
        self.assertIn('F-Score = Rentabilidad (4) + Apalancamiento/Liquidez (3) + Eficiencia Operativa (2)', content)
        self.assertIn('Mohanram G-Score (0-8)', content)
        self.assertIn('G-Score = Rentabilidad sobre Mediana (3) + Estabilidad (2) + Esfuerzo I+D/CapEx (3)', content)
        self.assertIn('ROIC_adj = NOPAT / (Capital Invertido + Intangibles I+D 5Y)', content)
        self.assertIn('Novy-Marx GP/A (2013)', content)
        self.assertIn('GP/A Total = Beneficio Bruto / Activos Totales', content)

        # 3. Pestaña 5: Auditoría Forense & Solvencia Financiera presente con tooltips grounded
        self.assertIn('id="tab-forensic"', content)
        self.assertIn('Ratio de Sloan (1996)', content)
        self.assertIn('Sloan Ratio = (Utilidad Neta − CFO) / Activos Medios', content)
        self.assertIn('Montier C-Score (0 a 6)', content)
        self.assertIn('Deuda Neta / EBITDA = (Deuda Total − Tesorería) / EBITDA', content)
        self.assertIn("Altman Z''-Score", content)
        self.assertIn("6.56 X₁ + 3.26 X₂ + 6.72 X₃ + 1.05 X₄", content)

    def test_quality_and_forensic_fixes_5_points(self):
        """Verifica los 5 puntos corregidos: tooltips sin overflow, deuda canónica SSOT, rating sintético institucional, señales con datos comparativos y ranking sectorial poblado."""
        for ticker in ['AAPL', 'DECK']:
            response = self.client.get(f'/company/{ticker}/')
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8')

            # Punto 1: Tooltips grounded en tarjetas sin overflow-hidden que los recorte
            self.assertIn('group-hover/tip:opacity-100', content)
            self.assertIn('border border-slate-700 space-y-2 text-left', content)

            # Punto 2: Tabla 13.1 Apalancamiento sincronizada canónicamente con Balance General
            self.assertIn('Deuda Financiera Total', content)
            self.assertIn('Tesorería y Activos Líquidos', content)
            self.assertIn('Deuda Financiera Neta', content)
            if ticker == 'AAPL':
                self.assertIn('$84,297.0M', content)
                self.assertIn('$62,399.0M', content)
                self.assertIn('$21,898.0M', content)
                self.assertNotIn('+$21,898.0M', content)
            elif ticker == 'DECK':
                self.assertIn('$0.0M', content)
                self.assertIn('-$1,668.2M (Caja Neta)', content)

            # Punto 3: Rating Sintético con estilo institucional y dictamen multi-factor
            self.assertIn('Dictamen Institucional de Solvencia & Riesgo Crediticio', content)
            self.assertIn('bg-slate-900 text-white rounded-2xl', content)
            self.assertIn('Calificación de Grado Institucional Máximo', content)

            # Punto 4: Señales Cuantitativas Piotroski & Mohanram con datos comparativos
            self.assertIn('Contraste LTM vs Previo:', content)
            self.assertIn('Criterio de Aprobación:', content)
            self.assertIn('Contraste vs Sector / Estabilidad:', content)
            self.assertIn('Benchmark Exigido:', content)

            # Punto 5: Ranking Sectorial de Pares (Novy-Marx) poblado con competidores y métricas
            if ticker == 'AAPL':
                self.assertIn('AAPL', content)
                self.assertIn('NTAP', content)
                self.assertIn('DELL', content)
    def test_roic_adjusted_tooltip_values(self):
        """Verifica que el tooltip de ROIC Ajustado refleje los valores exactos en millones sin doble escalado."""
        response_aapl = self.client.get('/company/AAPL/')
        self.assertEqual(response_aapl.status_code, 200)
        content_aapl = response_aapl.content.decode('utf-8')
        
        # AAPL: NOPAT $134,859.4M / Cap. Inv. $269,400.0M = 50.1%
        self.assertIn('NOPAT <strong class="text-slate-300">$134,859.4M</strong> / Cap. Inv. <strong class="text-slate-300">$269,400.0M</strong> = <strong class="text-emerald-400">50.1%</strong>', content_aapl)
        self.assertNotIn('NOPAT <strong class="text-slate-300">$0.1M</strong>', content_aapl)

        response_deck = self.client.get('/company/DECK/')
        self.assertEqual(response_deck.status_code, 200)
        content_deck = response_deck.content.decode('utf-8')
        
        # DECK: NOPAT $998.6M / Cap. Inv. $2,040.5M = 48.9%
        self.assertIn('NOPAT <strong class="text-slate-300">$998.6M</strong> / Cap. Inv. <strong class="text-slate-300">$2,040.5M</strong> = <strong class="text-emerald-400">48.9%</strong>', content_deck)

    def test_dynamic_sales_growth_cagr_not_hardcoded_8_pct(self):
        """Verifica que el crecimiento histórico de ventas no esté hardcodeado al 8% y refleje el CAGR auditado de cada firma."""
        # 1. DECK: CAGR 5Y auditado es 16.5%
        res_deck = self.client.get('/company/DECK/')
        self.assertEqual(res_deck.status_code, 200)
        c_deck = res_deck.content.decode('utf-8')
        self.assertIn('CAGR Histórico (16.5%)', c_deck)
        self.assertIn('Referencia Histórica 5Y: 16.5% anual', c_deck)
        self.assertIn('value="16.50"', c_deck)
        self.assertNotIn('Referencia Histórica 5Y: 8.0% anual', c_deck)

        # 2. AAPL: CAGR 5Y auditado es 8.7%
        res_aapl = self.client.get('/company/AAPL/')
        self.assertEqual(res_aapl.status_code, 200)
        c_aapl = res_aapl.content.decode('utf-8')
        self.assertIn('CAGR Histórico (8.7%)', c_aapl)
        self.assertIn('Referencia Histórica 5Y: 8.7% anual', c_aapl)
        self.assertIn('value="8.70"', c_aapl)

    def test_nvda_segments_and_descriptions(self):
        """Verifica que los segmentos modernos y las descripciones institucionales de NVDA se rendericen con precisión."""
        res_nvda = self.client.get('/company/NVDA/')
        self.assertEqual(res_nvda.status_code, 200)
        c_nvda = html.unescape(res_nvda.content.decode('utf-8'))

        # Plataformas modernas
        self.assertIn('Data Center — Hyperscale', c_nvda)
        self.assertIn('Data Center — AI Clouds, Industrial & Enterprise', c_nvda)
        self.assertIn('Edge Computing', c_nvda)

        # Descripciones pedagógicas de plataformas
        self.assertIn('Grandes hiperescaladores de nube pública global: Microsoft Azure, AWS, Google Cloud, Meta, Oracle.', c_nvda)
        self.assertIn('Nubes nativas de IA (CoreWeave, Lambda), corporaciones privadas (banca, salud, manufactura) e iniciativas gubernamentales de IA Soberana.', c_nvda)
        self.assertIn('Ecosistema en el borde que consolida Gaming (GeForce RTX), Visualización Profesional (Omniverse), Automoción (DRIVE) y robótica OEM.', c_nvda)

        # Descripciones pedagógicas geográficas
        self.assertIn('Sede de los mayores laboratorios de IA (frontier models), hiperescaladores y clústeres Blackwell.', c_nvda)
        self.assertIn('Ecosistema ODM/OEM y centros de integración y ensamblaje de servidores (Foxconn, Quanta, Wistron).', c_nvda)
        self.assertIn('Demanda sujeta a controles de exportación y licencias regulatorias del Departamento de Comercio de EE.UU.', c_nvda)

        # KPIs superiores
        self.assertIn('Línea Principal: Data Center — Hyperscale', c_nvda)
        self.assertIn('Línea Secundaria: Data Center — AI Clouds, Industrial & Enterprise', c_nvda)
        self.assertIn('Región Principal: United States', c_nvda)

    def test_control_companies_segments_zero_regression(self):
        """Verifica que las empresas de control (AAPL y DECK) preserven su renderizado de segmentos intacto."""
        # AAPL
        res_aapl = self.client.get('/company/AAPL/')
        self.assertEqual(res_aapl.status_code, 200)
        c_aapl = res_aapl.content.decode('utf-8')
        self.assertIn('iPhone', c_aapl)
        self.assertIn('Services', c_aapl)
        self.assertIn('Greater China', c_aapl)

        # DECK
        res_deck = self.client.get('/company/DECK/')
        self.assertEqual(res_deck.status_code, 200)
        c_deck = res_deck.content.decode('utf-8')
        self.assertIn('UGG', c_deck)
        self.assertIn('HOKA', c_deck)
    def test_meta_segments_and_geography(self):
        """Verifica que los segmentos de negocio y geografía de META se rendericen sin duplicados y reconciliados con ingresos consolidados."""
        res_meta = self.client.get('/company/META/')
        self.assertEqual(res_meta.status_code, 200)
        c_meta = html.unescape(res_meta.content.decode('utf-8'))

        # 1. No duplicación de columna LTM
        self.assertNotIn('<th>LTM</th>\n                                    <th>LTM</th>', c_meta)
        self.assertNotIn('<th>LTM</th>\r\n                                    <th>LTM</th>', c_meta)

        # 2. Segmentos de Producto primarios y LTM auditado
        self.assertIn('Family of Apps', c_meta)
        self.assertIn('Reality Labs', c_meta)
        self.assertIn('$225,989M', c_meta)
        self.assertIn('99.0%', c_meta)
        self.assertIn('$2,258.0M', c_meta)
        self.assertIn('1.0%', c_meta)

        # 3. Subsegmentos identados de Family of Apps
        self.assertIn('↳ Advertising', c_meta)
        self.assertIn('↳ Other revenue', c_meta)
        self.assertIn('$222,607M', c_meta)
        self.assertIn('$3,382.0M', c_meta)

        # 4. Total Neto Consolidado
        self.assertIn('(=) Total Neto Consolidado', c_meta)
        self.assertIn('$228,247M', c_meta)

        # 5. Geografía: 4 regiones primarias reconciliadas
        self.assertIn('United States & Canada', c_meta)
        self.assertIn('$88,672M', c_meta)
        self.assertIn('38.8%', c_meta)
        self.assertIn('Europe', c_meta)
        self.assertIn('$53,069M', c_meta)
        self.assertIn('23.3%', c_meta)
        self.assertIn('Asia-Pacific', c_meta)
        self.assertIn('$61,238M', c_meta)
        self.assertIn('26.8%', c_meta)
        self.assertIn('Rest of World', c_meta)
        self.assertIn('$25,268M', c_meta)
        self.assertIn('11.1%', c_meta)

        # 6. Subregión United States (Regla 6: no imputación falsa en LTM)
        self.assertIn('↳ United States', c_meta)

    def test_capital_allocation_full_series_and_palette(self):
        """Verifica que Asignación de Capital use recompras puras de mercado abierto, sume los años fiscales cerrados en las tarjetas (Opción 2) y aplique la paleta de alto contraste."""
        import re
        for ticker in ['META', 'AAPL', 'DECK']:
            res = self.client.get(f'/company/{ticker}/')
            self.assertEqual(res.status_code, 200)
            content = html.unescape(res.content.decode('utf-8'))

            # 1. Etiquetas de tarjetas acumuladas
            self.assertIn('Retorno Total al Accionista (Acum.)', content)
            self.assertIn('Reinversión Orgánica (CapEx Acum.)', content)
            self.assertIn('Flujo de Caja Operativo (Acum.)', content)

            # 2. Ventana auditada en tarjetas = años fiscales cerrados (sin duplicar el último FY con LTM), y gráfico hasta LTM
            m = re.search(r'const chartAllocData = (\{.*?\});', content)
            self.assertIsNotNone(m, f"chartAllocData not found in {ticker}")
            chart_alloc = json.loads(m.group(1))
            annual_labels = [lbl for lbl in chart_alloc['labels'] if lbl != 'LTM']
            expected_label = f"{annual_labels[0]}-{annual_labels[-1]}"
            self.assertIn(expected_label, content)
            self.assertEqual(chart_alloc['labels'][-1], 'LTM')

            # 3. Verificación explícita de recompras puras en META (sin contaminación de impuestos RSU)
            if ticker == 'META':
                self.assertEqual(
                    chart_alloc['buybacks'],
                    [1976.0, 12879.0, 4202.0, 6272.0, 44537.0, 27956.0, 19774.0, 30125.0, 26248.0, 3327.0]
                )
                self.assertIn('$184,365.0M', content)  # Retorno Total al Accionista (FY2017-FY2025)
                self.assertIn('$234,781.0M', content)  # CapEx Acum. (FY2017-FY2025)
                self.assertIn('$514,950.0M', content)  # CFO Acum. (FY2017-FY2025)

            # 4. Nueva paleta institucional de alto contraste en leyenda HTML y Chart.js
            self.assertIn('bg-blue-600', content)
            self.assertIn('bg-purple-600', content)
            self.assertIn('bg-amber-500', content)
            self.assertIn('bg-rose-600', content)
            self.assertIn('bg-emerald-600', content)
            self.assertIn("borderColor: '#059669'", content)
            self.assertIn("borderColor: '#2563eb'", content)
            self.assertIn("borderColor: '#9333ea'", content)
            self.assertIn("borderColor: '#f59e0b'", content)
            self.assertIn("borderColor: '#e11d48'", content)

    def test_novy_marx_sector_peer_ranking_all_companies(self):
        """Verifica que el Ranking Competitivo Sectorial (Peer Group Novy-Marx) en Calidad de Negocio nunca esté vacío y muestre la empresa objetivo sincronizada con sus pares."""
        expected_peers_by_ticker = {
            'META': ['GOOGL', 'MSFT', 'NFLX', 'SPOT', 'PINS', 'SNAP'],
            'AAPL': ['DELL', 'HPQ', 'NTAP', 'SMCI'],
            'DECK': ['NKE', 'ONON', 'CROX', 'SKX'],
            'JPM': ['BAC', 'WFC', 'C', 'GS', 'MS'],
            'O': ['PLD', 'SPG', 'VICI', 'NNN'],
            'PGR': ['CB', 'TRV', 'ALL', 'HIG'],
            'MELI': ['AMZN', 'SE'],
            'NU': ['SOFI', 'INTR'],
            'NVDA': ['AVGO', 'AMD', 'TSM', 'QCOM'],
        }
        for ticker, sample_peers in expected_peers_by_ticker.items():
            res = self.client.get(f'/company/{ticker}/')
            self.assertEqual(res.status_code, 200, f"HTTP error on /company/{ticker}/")
            content = html.unescape(res.content.decode('utf-8'))

            start_q = content.find('id="tab-quality"')
            end_q = content.find('id="tab-forensic"')
            self.assertTrue(start_q != -1 and end_q != -1, f"tab-quality not found in {ticker}")
            tab_quality = content[start_q:end_q]

            # 1. Nunca debe aparecer el mensaje de tabla vacía
            self.assertNotIn(
                'No se encontraron datos de pares para este sector.',
                tab_quality,
                f"Empty peer ranking table rendered for {ticker}"
            )

            # 2. La empresa objetivo debe estar presente y resaltada (bg-sky-50 font-bold text-slate-900 border-l-4 border-sky-500)
            self.assertIn('bg-sky-50 font-bold text-slate-900 border-l-4 border-sky-500', tab_quality, f"Target row highlight missing for {ticker}")
            self.assertIn(f'>{ticker}</span>', tab_quality, f"Target ticker {ticker} missing in peer table")

            # 3. Los competidores sectoriales esperados deben figurar en la tabla
            for peer_t in sample_peers:
                self.assertIn(f'>{peer_t}</span>', tab_quality, f"Expected peer {peer_t} missing in {ticker} peer table")


if __name__ == '__main__':
    unittest.main()



