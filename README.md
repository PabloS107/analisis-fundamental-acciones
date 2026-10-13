# Asistente de Análisis Fundamental de Acciones

Sistema modular para análisis fundamental automatizado, riguroso y libre de intermediarios financieros.

---

## Estructura del Sistema

```text
Analisis fundamental de acciones/
├── .agents/
│   └── skills/
│       └── fundamental-data-extractor/      <- Skill Antigravity registrada
│           ├── SKILL.md                     <- Instrucciones maestras del extractor
│           ├── scripts/
│           │   ├── fundamental_pipeline.py  <- Orquestador maestro
│           │   ├── sec_extractor.py         <- Extractor oficial SEC EDGAR (XBRL)
│           │   └── doc_parser.py            <- Lector de PDFs y Transcripciones de Drive
│           └── references/
│               └── schemas.md               <- Esquema estándar de datos JSON/Excel
├── web_dashboard/                           <- Plataforma Web Django (Visualizador Interactivo)
│   ├── manage.py
│   ├── analytics/                           <- Vistas de lectura dinámica de data/processed/
│   └── templates/                           <- Plantillas HTML responsivas (Chart.js + Tailwind)
├── Iniciar_Dashboard_Web.bat                <- Lanzador directo en 1 clic (abre navegador y servidor)
├── config/
│   └── sec_config.json                      <- Configuración SEC e identidad
├── drive_input/                             <- Enlace directo a 'G:\Mi unidad\analisis fundamental'
└── data/
    └── processed/
        └── {TICKER}/                        <- Salidas estructuradas por empresa
            ├── Analisis_Resultados_..._{TICKER}.docx        <- Informe institucional de 14 secciones
            ├── Analisis_Resultados_..._{TICKER}.md          <- Versión Markdown sincronizada
            ├── financial_statements.json                    <- Estados financieros auditados
            └── fundamental_scores.json                      <- Scores cuantitativos, solvencia y valoración

---

## Visualización y Navegación Interactiva (Django)

La visualización de datos se centraliza en la plataforma web **Django** (`web_dashboard/`):
- **Sin generar HTMLs estáticos sueltos por empresa:** Toda nueva empresa procesada en `data/processed/<TICKER>/` aparece automáticamente en el catálogo y tiene su panel interactivo en `http://127.0.0.1:8000/company/<TICKER>/`.
- **Acceso rápido con 1 clic:** Ejecutar `Iniciar_Dashboard_Web.bat` en la raíz del proyecto o en Google Drive.
- **Módulos incluidos:** Cuadro de Mando (KPIs), Gráficos dinámicos (Chart.js), Estados Financieros con buscador en tiempo real, Descomposición DuPont de Novy-Marx, Auditoría Forense y Simulador de Reverse DCF con deslizadores en vivo.

---

## Cómo usar el Extractor

### 1. Ingesta desde Google Drive (Opcional para material cualitativo)
En tu Google Drive (`G:\Mi unidad\analisis fundamental\<TICKER>\`):
- Deposita las diapositivas de presentaciones en la subcarpeta `presentations/` (formato `.pdf`).
- Deposita las transcripciones de las llamadas de resultados en `transcripts/` (formato `.txt`, `.md` o `.pdf`).

### 2. Ejecutar la Extracción y Análisis
Basta con pedirle al asistente:
> *"Extrae los datos fundamentales de Microsoft (MSFT)"* o *"Actualiza el análisis de AAPL"*.

O mediante terminal:
```powershell
python .agents/skills/fundamental-data-extractor/scripts/fundamental_pipeline.py --ticker MSFT
```

Los resultados se guardarán tanto en la carpeta local `data/processed/<TICKER>/` como directamente en tu Google Drive en `G:\Mi unidad\analisis fundamental\<TICKER>\processed\`. Al finalizar, la empresa estará disponible de inmediato en la plataforma web de Django.
