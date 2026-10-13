from pathlib import Path
import json

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"

def nav_companies(request):
    """
    Context processor universal que provee la lista dinámica de empresas
    analizadas con datos procesados válidos a todas las plantillas.
    """
    companies = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.iterdir(), key=lambda x: x.name):
            if d.is_dir() and not d.name.startswith("-") and not d.name.startswith("."):
                scores_file = d / "fundamental_scores.json"
                fin_file = d / "financial_statements.json"
                if scores_file.exists() or fin_file.exists():
                    ticker = d.name.upper()
                    name = ticker
                    if scores_file.exists():
                        try:
                            with open(scores_file, "r", encoding="utf-8") as f:
                                sc = json.load(f)
                                name = sc.get("company_name", ticker)
                        except Exception:
                            pass
                    companies.append({
                        "ticker": ticker,
                        "name": name,
                    })
    return {"nav_companies": companies}
